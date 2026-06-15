import json
import re
import glob
import os

GOLD_FILES = glob.glob("../Test_Files/Matched_patients/matched_patient-*.json")

OUTPUT_DIR = "./llm-outputs/matching-patients/"
OUTPUT_FILES = glob.glob(f"{OUTPUT_DIR}/*-experiment-clean.txt")

SAVE_DIR = "./manual-evaluations/patient-matching/"
os.makedirs(SAVE_DIR, exist_ok=True)

print(f"Found output files: {OUTPUT_FILES}\n")
print(f"Found gold files: {GOLD_FILES}\n")

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

def manual_compare(gold_item, pred_item):
    print("\n=== Manual Evaluation ===")
    print(f"CRITERION:\n  {gold_item['criterion']}")
    print(f"GOLD MATCH: {gold_item['match']}")
    print(f"PRED MATCH: {pred_item.get('match')}")
    print(f"GOLD JUSTIFICATION:\n  {gold_item['justification']}")
    print(f"PRED JUSTIFICATION:\n  {pred_item.get('justification')}")

    while True:
        ans = input("Is this correct? (y/n/partial): ").strip().lower()
        if ans in ["y", "n", "partial"]:
            return ans
        print("Please answer with y, n, or partial.")

for output_file in OUTPUT_FILES:
    print(f"\n\nEvaluating output file {output_file}\n")

    exp_name = os.path.basename(output_file).replace(".txt", "")

    with open(output_file, "r", encoding="utf-8") as out:
        output_text = out.read()

        for gold_file in GOLD_FILES:

            filename = os.path.basename(gold_file)
            patient_id = filename.split("matched_patient-")[1].replace(".json", "")

            print(f"\n=== Patient {patient_id} ===")

            save_path = os.path.join(SAVE_DIR, f"manual_eval_{exp_name}_patient-{patient_id}.json")
            if os.path.exists(save_path):
                print("Already evaluated, skipping.")
                continue

            with open(gold_file, "r", encoding="utf-8") as gf:
                gold_data = json.load(gf)

            outputs = output_text.split("Output for file ")
            outputs.pop(0)

            pattern = rf"diary_patient_{patient_id}\.txt"

            predicted = []

            for block in outputs:
                if re.search(pattern, block):
                    pred = safe_json_extract(block)
                    if pred:
                        predicted.append(pred)

            pred_map = {item["criterion"]: item for item in predicted}

            manual_results = {}

            for gold_item in gold_data:
                crit = gold_item["criterion"]

                if crit not in pred_map:
                    print(f"\nNo predicted output found for criterion:\n  {crit}")
                    ans = input("Mark as wrong? (y/n/partial): ").strip().lower()
                    manual_results[crit] = ans
                    continue

                pred_item = pred_map[crit]
                ans = manual_compare(gold_item, pred_item)
                manual_results[crit] = ans

            total = len(manual_results)
            correct = sum(1 for v in manual_results.values() if v == "y")
            partial = sum(1 for v in manual_results.values() if v == "partial")
            wrong = sum(1 for v in manual_results.values() if v == "n")

            human_accuracy = correct / total * 100 if total else 100
            partial_score = (correct + 0.5 * partial) / total * 100 if total else 100

            with open(save_path, "w", encoding="utf-8") as f:
                json.dump({
                    "patient": patient_id,
                    "manual_results": manual_results,
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
