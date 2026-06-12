import json
import re
import glob
import os

GOLD_FILES = glob.glob("../Test_Files/Clinical_trials/Criteria_extracted/clinical-trial-extracted_e*.txt")
OUTPUT_DIR = "./llm-outputs/criteria-extraction/"
OUTPUT_FILES = glob.glob(f"{OUTPUT_DIR}/*-experiment-*.txt")

SAVE_DIR = "./manual-evaluations/cohort-assignment/"
os.makedirs(SAVE_DIR, exist_ok=True)

def safe_json_extract(text):
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            return obj
        except Exception:
            continue
    return None

def extract_cohort_criteria(data, key):
    """Return list of (text, cohort_id) only for cohort-specific criteria."""
    out = []
    for item in data.get(key, []):
        if isinstance(item, dict):
            cid = item.get("cohort_id")
            if cid not in [None, "", "null"]:
                out.append((item.get("text"), cid))
    return out

for output_file in OUTPUT_FILES:
    print(f"\n\nEvaluating output file {output_file}\n")

    exp_name = os.path.basename(output_file).replace(".txt", "")

    with open(output_file, "r", encoding="utf-8") as out:
        output_text = out.read()

        for gold_file in GOLD_FILES:

            # Extract trial ID
            filename = os.path.basename(gold_file)
            trial_id = filename.split("_")[-1].replace(".txt", "")
            print(f"\n=== Trial {trial_id} ===")

            save_path = os.path.join(SAVE_DIR, f"manual_eval_{exp_name}_trial-{trial_id}.json")
            if os.path.exists(save_path):
                print("Already evaluated, skipping.")
                continue

            # Load GOLD
            with open(gold_file, "r", encoding="utf-8") as gf:
                gold_text = gf.read()
                gold_data = safe_json_extract(gold_text)

            if gold_data is None:
                print("Could not parse GOLD JSON.")
                continue

            # Extract cohort-specific criteria from GOLD
            gold_incl = extract_cohort_criteria(gold_data, "inclusion_criteria")
            gold_excl = extract_cohort_criteria(gold_data, "exclusion_criteria")
            gold_all = gold_incl + gold_excl

            # If GOLD has no cohort-specific criteria → auto 100%
            if len(gold_all) == 0:
                print("No cohort-specific criteria in GOLD → auto 100% accuracy.")
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "trial": trial_id,
                        "assignments": [],
                        "metrics": {
                            "correct": 0,
                            "partial": 0,
                            "wrong": 0,
                            "total": 0,
                            "human_accuracy": 100.0,
                            "partial_score": 100.0
                        }
                    }, f, indent=4, ensure_ascii=False)
                continue

            # Extract predicted JSON
            outputs = output_text.split("Ouput for file ")
            outputs.pop(0)

            pattern = rf"clinical-trial_{trial_id}\.txt"
            pred_data = None

            for block in outputs:
                if re.search(pattern, block):
                    pred_data = safe_json_extract(block)
                    break

            if pred_data is None:
                print("Could not parse predicted JSON.")
                continue

            # Extract cohort-specific criteria from PREDICTED
            pred_incl = extract_cohort_criteria(pred_data, "inclusion_criteria")
            pred_excl = extract_cohort_criteria(pred_data, "exclusion_criteria")
            pred_all = pred_incl + pred_excl

            print("\n=== GOLD COHORT-SPECIFIC CRITERIA ===")
            for i, (txt, cid) in enumerate(gold_all):
                print(f"[{i}] cohort_id={cid} → {txt}")

            print("\n=== PREDICTED COHORT-SPECIFIC CRITERIA ===")
            for j, (txt, cid) in enumerate(pred_all):
                print(f"[{j}] cohort_id={cid} → {txt}")

            print("\nAssign each GOLD criterion to a predicted one.")
            print("Type the predicted index (e.g., 0,1,2) or 'none' or 'partial'.")

            results = []
            for i, (gtext, gcohort) in enumerate(gold_all):
                ans = input(f"\nWhich predicted matches GOLD [{i}]? ").strip().lower()
                results.append(ans)

            # Metrics
            total = len(results)
            correct = sum(1 for r in results if r.isdigit())
            partial = results.count("partial")
            wrong = results.count("none")

            human_accuracy = correct / total * 100 if total else 100
            partial_score = (correct + 0.5 * partial) / total * 100 if total else 100

            with open(save_path, "w", encoding="utf-8") as f:
                json.dump({
                    "trial": trial_id,
                    "assignments": results,
                    "metrics": {
                        "correct": correct,
                        "partial": partial,
                        "wrong": wrong,
                        "total": total,
                        "human_accuracy": human_accuracy,
                        "partial_score": partial_score
                    }
                }, f, indent=4, ensure_ascii=False)

            print(f"\nSaved evaluation to {save_path}\n")
