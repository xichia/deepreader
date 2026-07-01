"""
Synthetic Gemini Batch-Size Escalation Canary Validation Script.

WARNING: This consumes live Gemini quota when provider-backed summaries are enabled.
This script is for manual execution only and must not be run as part of the automated build.
Ensure sufficient quota headroom before running.

Credential Safety Warning:
- Gemini API credentials must already be exported in the shell.
- Do not print secrets.
- Do not commit .env.local.
- This helper intentionally does not source .env.local.

Future Native-Terminal commands:

Scenario A: Batch size 10, provider cap 2
  Terminal 1 (paragraph-summary-service, from repository root):
    SUMMARY_SERVICE_PROVIDER=gemini \\
    SUMMARY_SERVICE_MODEL=gemini-3.1-flash-lite \\
    SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true \\
    SUMMARY_BATCH_MAX_RECORDS=10 \\
    SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=2 \\
    SUMMARY_LANE_RPM=15 \\
    PYTHONPATH=services/paragraph-summary-service \\
    uv run --project services/paragraph-summary-service uvicorn app.main:app --host 127.0.0.1 --port 8001

  Terminal 2 (run escalation canary script):
    uv run --with 'httpx>=0.27' python scripts/canary_gemini_batch_escalation.py --total-records 12 --expected-provider gemini --expected-model gemini-3.1-flash-lite --max-provider-calls 2

Scenario B: Batch size 12, provider cap 1
  Terminal 1 (paragraph-summary-service, from repository root):
    SUMMARY_SERVICE_PROVIDER=gemini \\
    SUMMARY_SERVICE_MODEL=gemini-3.1-flash-lite \\
    SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true \\
    SUMMARY_BATCH_MAX_RECORDS=12 \\
    SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1 \\
    SUMMARY_LANE_RPM=15 \\
    PYTHONPATH=services/paragraph-summary-service \\
    uv run --project services/paragraph-summary-service uvicorn app.main:app --host 127.0.0.1 --port 8001

  Terminal 2 (run escalation canary script):
    uv run --with 'httpx>=0.27' python scripts/canary_gemini_batch_escalation.py --total-records 12 --expected-provider gemini --expected-model gemini-3.1-flash-lite --max-provider-calls 1

Scenario C: Batch size 16, provider cap 1, textbook-hard
  Terminal 1 (paragraph-summary-service, from repository root):
    SUMMARY_SERVICE_PROVIDER=gemini \\
    SUMMARY_SERVICE_MODEL=gemini-3.1-flash-lite \\
    SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true \\
    SUMMARY_BATCH_MAX_RECORDS=16 \\
    SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1 \\
    SUMMARY_LANE_RPM=15 \\
    PYTHONPATH=services/paragraph-summary-service \\
    uv run --project services/paragraph-summary-service uvicorn app.main:app --host 127.0.0.1 --port 8001

  Terminal 2 (run escalation canary script):
    uv run --with 'httpx>=0.27' python scripts/canary_gemini_batch_escalation.py --total-records 16 --profile textbook-hard --words-per-record 180 --expected-provider gemini --expected-model gemini-3.1-flash-lite --max-provider-calls 1

Scenario D: Batch size 20, provider cap 1, textbook-hard
  Terminal 1 (paragraph-summary-service, from repository root):
    SUMMARY_SERVICE_PROVIDER=gemini \\
    SUMMARY_SERVICE_MODEL=gemini-3.1-flash-lite \\
    SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true \\
    SUMMARY_BATCH_MAX_RECORDS=20 \\
    SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1 \\
    SUMMARY_LANE_RPM=15 \\
    PYTHONPATH=services/paragraph-summary-service \\
    uv run --project services/paragraph-summary-service uvicorn app.main:app --host 127.0.0.1 --port 8001

  Terminal 2 (run escalation canary script):
    uv run --with 'httpx>=0.27' python scripts/canary_gemini_batch_escalation.py --total-records 20 --profile textbook-hard --words-per-record 180 --expected-provider gemini --expected-model gemini-3.1-flash-lite --max-provider-calls 1
"""

import argparse
import asyncio
import hashlib
import sys
import uuid
import httpx

def str_to_bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def build_simple_record(i, words_per_record):
    base_text = f"Synthetic paragraph content {i} to test batch-size escalation without external file dependencies."
    words = base_text.split()
    if len(words) >= words_per_record:
        return " ".join(words[:words_per_record])
    padding = [f"word{j}" for j in range(words_per_record - len(words))]
    return base_text + " " + " ".join(padding)

def build_textbook_hard_record(i, words_per_record, include_equations, include_crossrefs):
    topic_families = [
        {
            "concept": "Newtonian gravity and orbital decay",
            "prose_1": "Under the classical framework of Newtonian mechanics, the gravitational force acting between two spherical bodies of mass M and m is inversely proportional to the square of the distance r separating their barycenters. Consequently, the orbital trajectory of the lighter companion exhibits stability unless perturbed by non-conservative forces such as atmospheric drag or tidal friction.",
            "equation": r"F = G \frac{M \cdot m}{r^2}",
            "cause_effect": "Because the drag force dissipates kinetic energy, the orbital radius must decrease over time, which subsequently increases the orbital velocity of the satellite, leading to a localized heating event and eventual re-entry. Thus, an initial energy loss paradoxically causes a velocity increase.",
            "example": "For instance, consider a satellite orbiting at an altitude of 300 kilometers; its lifetime is bounded by the local atmospheric density profile.",
            "crossref": "as discussed in Section 4.2",
            "caveat": "However, this model assumes a spherical mass distribution and neglects relativistic precession effects.",
            "parenthetical": "(which are modeled separately using Einstein's field equations)"
        },
        {
            "concept": "cellular respiration and ATP synthesis",
            "prose_1": "Cellular respiration represents the primary metabolic pathway through which aerobic organisms convert biochemical energy from nutrients into adenosine triphosphate (ATP). The inner mitochondrial membrane hosts the electron transport chain, creating a critical electrochemical proton gradient across the intermembrane space.",
            "equation": r"\Delta p = \Delta \psi - \frac{2.3 RT}{F} \Delta pH",
            "cause_effect": "As electrons flow through the transmembrane complexes, protons are actively pumped into the intermembrane space, generating a proton-motive force that drives protons back through the ATP synthase channel, resulting in the phosphorylation of ADP to ATP.",
            "example": "For example, the oxidation of one NADH molecule yields approximately 2.5 molecules of ATP under standard physiological conditions.",
            "crossref": "as discussed in Section 7.5",
            "caveat": "Nevertheless, this stoichiometric ratio varies depending on the specific shuttle system utilized.",
            "parenthetical": "(such as the malate-aspartate shuttle versus the glycerol-3-phosphate shuttle)"
        },
        {
            "concept": "chemical equilibrium and Le Chatelier's principle",
            "prose_1": "In closed thermodynamic systems, chemical equilibrium is achieved when the rates of the forward and reverse reactions are equal, resulting in stable macroscopic concentrations. The reaction quotient Q dynamically approaches the equilibrium constant K over time.",
            "equation": r"\Delta G = \Delta G^\circ + RT \ln Q",
            "cause_effect": "If a stress is applied to the system by altering the pressure, temperature, or concentration of reactants, the equilibrium position shifts in the direction that counteracts the perturbation, thereby restoring equilibrium status.",
            "example": "To illustrate, increasing the concentration of reactants forces the system to produce more products until Q equals K again.",
            "crossref": "as discussed in Section 3.1",
            "caveat": "Be aware that adding a catalyst accelerates both rates equally without shifting the equilibrium position.",
            "parenthetical": "(although it significantly reduces the time required to reach this state)"
        },
        {
            "concept": "macroeconomics supply-demand elasticity",
            "prose_1": "Microeconomic analysis shows that price elasticity of demand measures the responsiveness of quantity demanded to a change in the product's price. When demand is elastic, consumers are highly sensitive to price fluctuations.",
            "equation": r"\epsilon_d = \frac{\% \Delta Q_d}{\% \Delta P}",
            "cause_effect": "Because a price increase causes a larger percentage drop in quantity demanded for elastic goods, total revenue will decrease following a price hike, leading firms to adopt alternative pricing strategy to maximize profits.",
            "example": "As an illustration, a 10% increase in luxury goods pricing might lead to a 20% reduction in sales.",
            "crossref": "as discussed in Section 11.2",
            "caveat": "Note that this elasticity is not constant along a linear demand curve.",
            "parenthetical": "(varying from infinity at the vertical axis to zero at the horizontal axis)"
        },
        {
            "concept": "thermodynamics and entropy",
            "prose_1": "The second law of thermodynamics establishes that the total entropy of an isolated system always increases over time, approaching a maximum value at equilibrium. Entropy serves as a quantitative measure of microscopic disorder.",
            "equation": r"S = k_B \ln \Omega",
            "cause_effect": "Since heat spontaneously flows from hotter bodies to colder bodies, thermal energy dispersion increases the number of microstates available to the system, causing an irreversible degradation of useful energy.",
            "example": "For instance, when hot water mixes with cold water, the final mixed state possesses higher entropy.",
            "crossref": "as discussed in Section 6.4",
            "caveat": "Strictly speaking, local entropy decreases are possible if work is performed by the external environment.",
            "parenthetical": "(as observed in refrigeration cycles)"
        }
    ]

    tf = topic_families[i % len(topic_families)]
    parts = []
    parts.append(f"Regarding {tf['concept']}:")
    parts.append(tf['prose_1'])
    if include_equations:
        parts.append(f"This relation is mathematically defined as: $${tf['equation']}$$")
    parts.append(tf['cause_effect'])
    parts.append(tf['example'])
    if include_crossrefs:
        parts.append(f"({tf['crossref']}).")
    parts.append(tf['caveat'])
    parts.append(tf['parenthetical'])

    full_text = " ".join(parts)
    words = full_text.split()
    if len(words) >= words_per_record:
        return " ".join(words[:words_per_record])

    padding_sentences = [
        "Furthermore, detailed empirical studies confirm this theoretical baseline across multiple trials.",
        "The quantitative agreement between observations and model predictions remains exceptionally high.",
        "Researchers must account for environmental fluctuations during experimental verification phases.",
        "Under these constraints, the general equations simplify to their first-order linear approximations.",
        "These relationships form the foundation of modern textbook analytical physics and chemistry."
    ]
    idx = 0
    while len(words) < words_per_record:
        sentence = padding_sentences[idx % len(padding_sentences)]
        words.extend(sentence.split())
        idx += 1

    return " ".join(words[:words_per_record])

async def main():
    parser = argparse.ArgumentParser(description="Canary Gemini Batch Escalation Test")
    parser.add_argument("--total-records", type=int, default=12)
    parser.add_argument("--expected-provider", type=str, default="gemini")
    parser.add_argument("--expected-model", type=str, default="gemini-3.1-flash-lite")
    parser.add_argument("--max-provider-calls", type=int, default=None)
    parser.add_argument("--require-zero-429", type=str_to_bool, default=True)
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8001")
    parser.add_argument("--profile", type=str, choices=["simple", "textbook-hard"], default="simple")
    parser.add_argument("--words-per-record", type=int, default=None)
    parser.add_argument("--include-equations", type=str_to_bool, default=True)
    parser.add_argument("--include-crossrefs", type=str_to_bool, default=True)
    args = parser.parse_args()

    # Determine words per record if not provided
    words_per_record = args.words_per_record
    if words_per_record is None:
        if args.profile == "simple":
            words_per_record = 15
        else:
            words_per_record = 180

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Check health and verify provider/model configuration
        try:
            res = await client.get(f"{args.base_url}/health")
            res.raise_for_status()
            health_data = res.json()
        except Exception as e:
            print(f"FAIL: Paragraph-summary-service not reachable at {args.base_url}: {e}")
            sys.exit(1)

        health_provider = health_data.get("provider") or health_data.get("summary_service_provider")
        health_settings = health_data.get("settings", {})
        health_model = health_settings.get("model") or health_settings.get("summary_service_model") or health_data.get("model")

        # Submit synthetic records
        doc_id = str(uuid.uuid4())
        records = []
        total_input_words = 0
        for i in range(args.total_records):
            if args.profile == "simple":
                text = build_simple_record(i, words_per_record)
            else:
                text = build_textbook_hard_record(i, words_per_record, args.include_equations, args.include_crossrefs)
            source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            total_input_words += len(text.split())
            records.append({
                "record_id": f"rec-{i}",
                "stable_id": f"rec-{i}",
                "text": text,
                "source_hash": source_hash,
                "metadata": {}
            })

        print(f"profile: {args.profile}")
        print(f"words_per_record: {words_per_record}")
        print(f"total approximate input words: {total_input_words}")
        print(f"total records: {args.total_records}")
        print(f"expected provider/model: {args.expected_provider}/{args.expected_model}")
        print(f"health provider/model: {health_provider}/{health_model}")

        # Check if provider matches what we expect
        if args.expected_provider and health_provider != args.expected_provider:
            print(f"FAIL: Expected provider '{args.expected_provider}', but health shows '{health_provider}'")
            sys.exit(1)

        # Check if model matches what we expect
        if args.expected_model and health_model != args.expected_model:
            print(f"FAIL: Expected model '{args.expected_model}', but health shows '{health_model}'")
            sys.exit(1)

        payload = {
            "document_id": doc_id,
            "records": records,
            "summary_style": "one_sentence",
            "priority": "interactive"
        }

        print(f"Submitting job with {args.total_records} records...")
        try:
            submit_res = await client.post(f"{args.base_url}/paragraph-summaries", json=payload)
            submit_res.raise_for_status()
            job_data = submit_res.json()
            job_id = job_data["job_id"]
        except Exception as e:
            print(f"FAIL: Job submission failed: {e}")
            sys.exit(1)

        print(f"submitted total: {args.total_records}")
        print(f"Job ID: {job_id}")

        # Poll status
        while True:
            try:
                status_res = await client.get(f"{args.base_url}/jobs/{job_id}")
                status_res.raise_for_status()
                job = status_res.json()
            except Exception as e:
                print(f"FAIL: Querying job status failed: {e}")
                sys.exit(1)

            status = job["status"]
            if status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(1.0)

        stats = job.get("stats", {})
        provider_calls_attempted = stats.get("provider_calls_attempted", 0)
        rate_limit_count = stats.get("rate_limit_count", 0)

        eff = stats.get("effective_config", {})
        batch_max_records = eff.get("batch_max_records")
        max_provider_calls_per_job = eff.get("max_provider_calls_per_job")

        print(f"final status: {status}")
        print(f"completed/failed/total: {job['completed_records']}/{job['failed_records']}/{job['total_records']}")
        print(f"provider_calls_attempted: {provider_calls_attempted}")
        print(f"rate_limit_count: {rate_limit_count}")
        print(f"effective_config.batch_max_records: {batch_max_records}")
        print(f"effective_config.max_provider_calls_per_job: {max_provider_calls_per_job}")

        # Assertions
        failures = []

        if status != "completed":
            failures.append(f"Job status is '{status}', expected 'completed'")
        if job["failed_records"] != 0:
            failures.append(f"Failed records is {job['failed_records']}, expected 0")
        if job["completed_records"] != args.total_records:
            failures.append(f"Completed records is {job['completed_records']}, expected {args.total_records}")
        if args.max_provider_calls is not None and provider_calls_attempted > args.max_provider_calls:
            failures.append(f"provider_calls_attempted {provider_calls_attempted} exceeded limit {args.max_provider_calls}")
        if args.require_zero_429 and rate_limit_count != 0:
            failures.append(f"rate_limit_count is {rate_limit_count}, expected 0")

        if failures:
            print("\nFAILURES DETECTED:")
            for f in failures:
                print(f" - {f}")
            sys.exit(1)

        print("\nPASS: All batch escalation assertions satisfied.")

if __name__ == "__main__":
    asyncio.run(main())
