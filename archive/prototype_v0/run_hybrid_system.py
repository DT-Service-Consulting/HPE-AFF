import argparse
import json
from core_logic import extract_pdf_form_fields, extract_pdf_text, evolve_mappings, fill_pdf_form
from intelligent_router import DeploymentRouter
import project_secrets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--population", type=int, default=5)
    args = parser.parse_args()

    with open(args.data, "r", encoding="utf-8") as f:
        user_data = json.load(f)

    fields = extract_pdf_form_fields(args.pdf)
    form_text = extract_pdf_text(args.pdf)

    router = DeploymentRouter(project_secrets.AZURE_MODEL_GENERATOR, project_secrets.AZURE_MODEL_CRITIC)
    chosen_model = router.choose_generator(len(fields), len(form_text))

    candidates = evolve_mappings(
        fields,
        user_data,
        form_text,
        generations=args.generations,
        population=args.population,
        generator_model=chosen_model,
        critic_model=project_secrets.AZURE_MODEL_CRITIC
    )

    best = candidates[0]
    output_pdf = "outputs/filled_hybrid.pdf"
    output_json = "outputs/best_mapping_hybrid.json"

    fill_pdf_form(args.pdf, output_pdf, best.mapping, user_data)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump({"chosen_model": chosen_model, "mapping": best.mapping}, f, indent=2)

    print("Chosen model:", chosen_model)
    print("Mapping saved to:", output_json)
    print("Filled PDF saved to:", output_pdf)


if __name__ == "__main__":
    main()
