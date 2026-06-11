import json
import re
import glob
import os
from groq import Groq
import logging
import time

logging.basicConfig(
    filename="criteria_extraction_eval.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

GROQ_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY)

TRIALS = glob.glob("../Test_Files/Clinical_trials/clinical-trial_e*.txt")
GOLD_FILES = glob.glob("../Test_Files/Clinical_trials/Criteria_extracted/clinical-trial-extracted_e*.txt")

OUTPUT_DIR = "./llm-outputs/criteria-extraction/"
OUTPUT_FILES = glob.glob(f"{OUTPUT_DIR}/*-experiment-*.txt")

SAVE_DIR = "./manual-evaluations/criteria-extraction"
os.makedirs(SAVE_DIR, exist_ok=True)

print(f"Found output files: {OUTPUT_FILES}")
print(f"Found gold files: {GOLD_FILES}")

def safe_json_extract(text):

    if not text:
        return None

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

def safe_criteria_list(data, key):

    values = data.get(key, [])

    if not isinstance(values, list):
        return []

    criteria = []

    for item in values:

        if isinstance(item, dict):

            text = item.get("text")

            if text and isinstance(text, str):
                criteria.append(text.strip())

        elif isinstance(item, str):

            criteria.append(item.strip())

    return criteria

def llm_evaluate_criterion(gold_text, pred_list):

    logging.info("Evaluating criterion: %s", gold_text)
    logging.info("Predicted list size: %d", len(pred_list))

    prompt = f"""
You are an expert in clinical trial eligibility criteria.

Your task is to evaluate how well a GOLD criterion matches the list of PREDICTED criteria produced by an LLM.

IMPORTANT RULES ABOUT MATCHING:
1. A single GOLD criterion may correspond to:
   - exactly one predicted criterion
   - multiple predicted criteria (if the model split the criterion)
   - none (if the model missed it)

2. A single predicted criterion may correspond to:
   - exactly one GOLD criterion
   - multiple GOLD criteria (if the model merged them)

3. Splitting or merging is NOT automatically wrong.
   You must classify based on semantic equivalence, not formatting.

   MERGING is considered correct when:
   - all the information from the GOLD criterion is present in the predicted text
   - no clinically meaningful details are lost
   - no additional constraints are added that change eligibility
   - the logical meaning is preserved (e.g., listing A and B separately is equivalent to "A or B")

   MERGING is considered partial when:
   - the predicted text adds extra conditions not present in the GOLD
   - or removes clinically relevant details
   - or changes the logical meaning (e.g., “A AND B” instead of “A OR B”)

   SPLITTING is considered correct when:
   - the predicted criteria collectively preserve the full meaning of the GOLD criterion
   - no details are lost

   SPLITTING is considered **partial** when:
   - only part of the GOLD criterion is captured
   - or important details are missing
   
4. Order does NOT matter.
   - You must evaluate based on semantic meaning, not position.

5. You must consider the clinical context.
   - For example, lab thresholds, disease definitions, prior therapy requirements, and cohort-specific rules.

YOUR OUTPUT:
Return ONLY valid JSON in this format:

{{
  "match_index": <index of best predicted criterion, or null>,
  "match_text": <text of best predicted criterion, or null>,
  "classification": "correct" | "partial" | "wrong",
  "explanation": "<short explanation>"
}}

GOLD CRITERION:
"{gold_text}"

PREDICTED CRITERIA:
{json.dumps(pred_list, indent=2)}
"""



    MAX_RETRIES = 5

    for attempt in range(MAX_RETRIES):

        try:

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0
            )

            content = response.choices[0].message.content

            logging.info(
                "Raw response for criterion '%s': %s",
                gold_text,
                content
            )

            json_match = re.search(
                r"\{.*\}",
                content,
                flags=re.DOTALL
            )

            if not json_match:
                raise ValueError(
                    f"No JSON found in response: {content}"
                )

            parsed = json.loads(json_match.group())

            return parsed

        except Exception as e:

            error_text = str(e)

            logging.error(
                "Attempt %s failed for criterion '%s': %s",
                attempt + 1,
                gold_text,
                error_text
            )

            if attempt < MAX_RETRIES - 1:

                wait_time = 15 * (attempt + 1)

                logging.info(
                    "Waiting %s seconds before retry...",
                    wait_time
                )

                time.sleep(wait_time)

            else:

                return {
                    "match_index": None,
                    "match_text": None,
                    "classification": "error",
                    "explanation": error_text
                }

for output_file in OUTPUT_FILES:
    print(f"\n\nEvaluating output file {output_file}\n\n")

    exp_name = os.path.basename(output_file).replace(".txt", "")

    with open(output_file, "r", encoding="utf-8") as out:
        output_text = out.read()

        for gold_file in GOLD_FILES:
            with open(gold_file, "r", encoding="utf-8") as gf:

                trial_id = os.path.basename(gold_file).replace("clinical-trial-extracted_", "").replace(".txt", "")
                print(f"\n=== Trial {trial_id} ===")

                expected_eval_file = os.path.join(
                    SAVE_DIR,
                    f"manual_eval_{exp_name}_trial-{trial_id}.json"
                )

                if os.path.exists(expected_eval_file):
                    print(f"Skipping trial {trial_id} for {exp_name} (already evaluated).")
                    logging.info(
                        "Skipping trial %s for experiment %s because %s already exists.",
                        trial_id, exp_name, expected_eval_file
                    )
                    continue

                gold_data = json.load(gf)

                outputs = output_text.split("Ouput for file ")
                outputs.pop(0)

                pattern = rf"clinical-trial_{re.escape(trial_id)}\.txt"

                for output in outputs:
                    if not re.search(pattern, output):
                        continue

                    pred_data = safe_json_extract(output)

                    if pred_data is None:
                        logging.error("Failed to parse prediction JSON for trial %s", trial_id)
                        print(f"Could not parse prediction JSON for {trial_id}")
                        continue

                    pred_inclusion = safe_criteria_list(pred_data, "inclusion_criteria")
                    pred_exclusion = safe_criteria_list(pred_data, "exclusion_criteria")

                    results_inclusion = []
                    results_exclusion = []

                    print("\nEvaluating inclusion criteria...")
                    for crit in gold_data.get("inclusion_criteria", []):
                        gold_text = crit["text"]
                        result = llm_evaluate_criterion(gold_text, pred_inclusion)
                        results_inclusion.append({"gold": gold_text, "evaluation": result})

                    print("\nEvaluating exclusion criteria...")
                    for crit in gold_data.get("exclusion_criteria", []):
                        gold_text = crit.get("text")
                        if not gold_text:
                            continue
                        result = llm_evaluate_criterion(gold_text, pred_exclusion)
                        results_exclusion.append({"gold": gold_text, "evaluation": result})

                    all_eval = results_inclusion + results_exclusion
                    classifications = [r["evaluation"]["classification"] for r in all_eval]

                    correct = classifications.count("correct")
                    partial = classifications.count("partial")
                    wrong = classifications.count("wrong")
                    errors = classifications.count("error")

                    valid_total = correct + partial + wrong

                    if valid_total == 0:
                        human_accuracy = 0
                        partial_score = 0
                    else:
                        human_accuracy = correct / valid_total * 100
                        partial_score = (correct + 0.5 * partial) / valid_total * 100

                    save_path = expected_eval_file

                    with open(save_path, "w", encoding="utf-8") as f:
                        json.dump({
                            "trial": trial_id,
                            "results": {
                                "inclusion": results_inclusion,
                                "exclusion": results_exclusion
                            },
                            "metrics": {
                                "correct": correct,
                                "partial": partial,
                                "wrong": wrong,
                                "errors": errors,
                                "evaluated": valid_total,
                                "human_accuracy": human_accuracy,
                                "partial_score": partial_score
                            }
                        }, f, indent=4, ensure_ascii=False)

                    print(f"\nSaved evaluation to {save_path}\n")
