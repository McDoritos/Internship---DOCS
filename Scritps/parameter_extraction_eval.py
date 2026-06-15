import json
import re
import glob
import os

DIARIES = glob.glob("../Test_Files/Clinical_diaries/inconsistancy-diary_patient_*.txt")
GOLD_FILES = glob.glob("../Test_Files/Clinical_diaries/Diaries-extracted/diary-extracted_patient_*.json")
NORMALIZATION_FILES = glob.glob("../Test_Files/Normalization_sheet/normalization-sheet*.csv")
SCHEMA = "../Test_Files/Schemas/parameter-extraction_schema.json"

OUTPUT_DIR = "./llm-outputs/parameter-extraction/"
OUTPUT_FILE = "experiment"
OUTPUT_FILES = glob.glob(f"{OUTPUT_DIR}/*-experiment-*.txt")

SAVE_DIR = "./manual-evaluations/"
os.makedirs(SAVE_DIR, exist_ok=True)

print(f"Found the following output files {OUTPUT_FILES}")
print(f"Found the following diaries {DIARIES}")
print(f"Found the following golden diaries {GOLD_FILES}")
print(f"Found the following normalization files {NORMALIZATION_FILES}")

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


for output_file in OUTPUT_FILES:
    print(f"\n\nEvaluating output file {output_file}\n\n")
    if "deepseek" in output_file:
        print("Skipping deepseek output file as it was already processed.")
        continue
    
    with open(output_file,"r",encoding="utf-8") as out:
        output_text = out.read()
        
        for gold_file in GOLD_FILES:
            with open(gold_file,"r",encoding="utf-8") as gf, \
                open(SCHEMA,"r",encoding="utf-8") as sch:

                curr_gf_diary = gold_file.split('_')[-2] + "_" + gold_file.split('_')[-1].split('.')[0]
                
                print(f"{curr_gf_diary}")
                
                data_gf = json.load(gf)
                data_sch = json.load(sch)

                outputs = output_text.split("Ouput for file ")
                outputs.pop(0)
                
                pattern = rf"diary_{re.escape(curr_gf_diary)}\b"
                
                for output in outputs:
                    if not re.search(pattern, output):
                        continue

                    json_match = re.search(r"\{.*\}", output, flags=re.DOTALL)
                    if not json_match:
                        print("No JSON found for", curr_gf_diary)
                        continue

                    output_json = json.loads(json_match.group(0))

                    print("Golden truth data ", data_gf)
                    print("Output of the LLM ", output_json)

                    manual_results = manual_compare(data_gf, output_json)
                    print("\nManual evaluation results:", manual_results)

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

                    exp_name = os.path.basename(output_file).replace(".txt", "")
                    save_path = os.path.join(SAVE_DIR, f"manual_eval_{exp_name}_{curr_gf_diary}.json")

                    with open(save_path, "w", encoding="utf-8") as f:
                        json.dump({
                            "diary": curr_gf_diary,
                            "manual_results": manual_results,
                            "metrics": {
                                "correct": correct,
                                "partial": partial,
                                "wrong": wrong,
                                "human_accuracy": human_accuracy,
                                "partial_score": partial_score
                            }
                        }, f, indent=4, ensure_ascii=False)

                    print(f"\nSaved manual evaluation to {save_path}\n")

                    gt_keys = set(data_sch.keys())
                    out_keys = set(output_json.keys())
                    matched_keys = gt_keys & out_keys

                    print(f"The output complied with {len(matched_keys)} out of {len(gt_keys)}, "
                        f"so we have a schema compliance rate of {(len(matched_keys)/len(gt_keys))*100}%")

                    out_num_missing = 0
                    for key, value in data_gf.items():
                        if value is not None:
                            if key not in output_json or output_json[key] in [None, "null", ""]:
                                out_num_missing += 1

                    print(f"The output could identify {out_num_missing} fields from the golden truth diary, "
                        f"so missing field rate is {(out_num_missing/len(data_gf))*100}%")

                    def normalize(x):
                        if isinstance(x, str) and x.isdigit():
                            return int(x)
                        return x

                    out_num_right = 0
                    for key in data_gf:
                        if key in output_json and normalize(data_gf[key]) == normalize(output_json[key]):
                            out_num_right += 1

                    print(f"Field-level accuracy: {out_num_right} out of {len(data_gf)} fields correctly identified, so we have a field-level accuracy of {(out_num_right/len(data_gf))*100}%")
