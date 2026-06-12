import json
import re
import glob
import os

GOLD_FILES = glob.glob("../Test_Files/Clinical_trials/Trial_structure/clinical-trial-structure_e*.txt")

OUTPUT_DIR = "./llm-outputs/trial-structure/"
OUTPUT_FILES = glob.glob(f"{OUTPUT_DIR}/*-experiment-*.txt")

SAVE_DIR = "./manual-evaluations/trial-structure/"
os.makedirs(SAVE_DIR, exist_ok=True)

print(f"Found output files: {OUTPUT_FILES}")
print(f"Found gold structures: {GOLD_FILES}")


def manual_compare(gold, pred):
    results = {}
    print("\n=== Manual Evaluation ===\n")

    for key in gold:
        gold_val = gold[key]
        pred_val = pred.get(key, None)

        print(f"\nField: {key}")
        print(f"  Gold: {gold_val}")
        print(f"  Pred: {pred_val}")

        while True:
            ans = input("Is this correct? (y/n/partial): ").strip().lower()
            if ans in ["y", "n", "partial"]:
                break
            print("Please answer with y, n, or partial.")

        results[key] = ans

    return results


def safe_json_extract(text):
    """Extract first valid JSON object from text."""
    decoder = json.JSONDecoder()

    for i, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            return obj
        except Exception:
            continue

    return None


for output_file in OUTPUT_FILES:
    print(f"\n\nEvaluating output file {output_file}\n\n")

    exp_name = os.path.basename(output_file).replace(".txt", "")

    with open(output_file, "r", encoding="utf-8") as out:
        output_text = out.read()

        for gold_file in GOLD_FILES:
            filename = os.path.basename(gold_file)
            trial_id = filename.split("_")[-1].replace(".txt", "")

            print(f"\n=== Trial {trial_id} ===")

            save_path = os.path.join(SAVE_DIR, f"manual_eval_{exp_name}_trial-{trial_id}.json")

            if os.path.exists(save_path):
                print(f"Skipping {trial_id}, already evaluated.")
                continue

            with open(gold_file, "r", encoding="utf-8") as gf:
                gold_text = gf.read()
                gold_struct = safe_json_extract(gold_text)

            if gold_struct is None:
                print(f"Could not parse GOLD JSON for {trial_id}")
                continue


            outputs = output_text.split("Ouput for file ")
            outputs.pop(0)

            pattern = rf"clinical-trial_{trial_id}\.txt"

            for output in outputs:
                if not re.search(pattern, output):
                    continue

                pred_struct = safe_json_extract(output)

                if pred_struct is None:
                    print(f"Could not parse predicted structure for {trial_id}")
                    continue

                print("\nGOLD STRUCTURE:")
                print(json.dumps(gold_struct, indent=2))

                print("\nPREDICTED STRUCTURE:")
                print(json.dumps(pred_struct, indent=2))

                manual_results = manual_compare(gold_struct, pred_struct)

                total = len(manual_results)
                correct = sum(1 for v in manual_results.values() if v == "y")
                partial = sum(1 for v in manual_results.values() if v == "partial")
                wrong = sum(1 for v in manual_results.values() if v == "n")

                human_accuracy = correct / total * 100
                partial_score = (correct + 0.5 * partial) / total * 100

                print("\n=== HUMAN METRICS ===")
                print(f"Correct: {correct}")
                print(f"Partial: {partial}")
                print(f"Wrong: {wrong}")
                print(f"Human accuracy (strict): {human_accuracy:.2f}%")
                print(f"Partial-aware score: {partial_score:.2f}%")

                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "trial": trial_id,
                        "manual_results": manual_results,
                        "metrics": {
                            "correct": correct,
                            "partial": partial,
                            "wrong": wrong,
                            "human_accuracy": human_accuracy,
                            "partial_score": partial_score
                        }
                    }, f, indent=4, ensure_ascii=False)

                print(f"\nSaved evaluation to {save_path}\n")
