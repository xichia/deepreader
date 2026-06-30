# Summary Service Configuration Presets

This document details static paragraph-summary-service batching and token-budget presets based on completed synthetic validation.

## 1. Purpose and Scope

* **Documentation Only**: The presets described here are for reference and planning only.
* **No Default Changes**: These presets do not modify any system configuration files or environment defaults.
* **Bounded Validation Planning**: These guidelines are intended solely for bounded validation planning and testing.

---

## 2. Safety Rules

When preparing or configuring any summary pipeline test, adhere strictly to the following safety rules:

* **Confirm Quota Headroom**: Verify that your provider quota is sufficient before starting any non-mocked runs.
* **Set Hard Provider-Call Caps**: Always set a strict limit on the maximum number of provider calls per job (`SUMMARY_MAX_PROVIDER_CALLS_PER_JOB`).
* **Start with Tiny Bounded Inputs**: Do not ingest large datasets initially. Start validation with very small document subsets.
* **Define Stop Conditions**: Clearly establish under what conditions (e.g., call budget reached, error rate threshold met) a validation job should abort.
* **OpenStax Restriction**: OpenStax must not be run without explicit approval.

---

## 3. Current / Conservative Preset

This preset represents the mock-based validation environment and the baseline default token budget configuration.

### Mock Lifecycle Validation
```ini
SUMMARY_SERVICE_PROVIDER=mock
SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=false
```

### Baseline Default Token Budget Configuration
```ini
SUMMARY_BATCH_TARGET_TOKENS=2000
SUMMARY_BATCH_HARD_MAX_TOKENS=3000
SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=1000
```

### Observed Behavior
Under this budget, hard synthetic validation indicates that roughly **4 records** can be processed per provider call at ~180 words per record. Adding a 5th record typically exceeds the budget, causing a split under a strict 1-call limit.

---

## 4. Balanced Synthetic-Validated Preset

This is the recommended configuration to use as the first candidate for future provider-backed validation.

### Configuration
```ini
SUMMARY_BATCH_MAX_RECORDS=16
SUMMARY_BATCH_TARGET_TOKENS=10000
SUMMARY_BATCH_HARD_MAX_TOKENS=14000
SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=3500
```

### Recommended Pairing
```ini
SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1
```

### Context
This is the safest documented configuration candidate for future bounded validation, offering a balanced tradeoff between batch density and token budget headroom.

---

## 5. Aggressive Validation-Only Preset

This preset increases the density limit and token budget to push the limits of single-call and multi-call scenarios.

### Configuration
```ini
SUMMARY_BATCH_MAX_RECORDS=24
SUMMARY_BATCH_TARGET_TOKENS=12000
SUMMARY_BATCH_HARD_MAX_TOKENS=16000
SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=4000
```

### Observed Behavior (Cap 1 vs. Cap 2)
* **Single Call Cap (`SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1`)**:
  * **Passed**: 20 records × ~240 synthetic words.
  * **Failed**: 22 records × ~240 synthetic words (failed due to retry or provider-call cap exhaustion).
* **Double Call Cap (`SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=2`)**:
  * **Passed**: 22 and 24 records × ~240 synthetic words.

> [!WARNING]
> This is strictly a validation-only configuration and is not recommended as a default.

---

## 6. Exploratory High-Ceiling Validation

An exploratory preset designed to test batch sizes at the upper bounds of token budgets.

### Configuration
```ini
SUMMARY_BATCH_MAX_RECORDS=32
SUMMARY_BATCH_TARGET_TOKENS=16000
SUMMARY_BATCH_HARD_MAX_TOKENS=22000
SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=6000
SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=2
```

### Observed Behavior
* **Passed (1 provider call)**: 26, 28, and 30 records × ~240 synthetic words.
* **Passed (2 provider calls)**: 32 records × ~240 synthetic words (successfully completed but required a second provider call).

> [!NOTE]
> This preset serves as headroom evidence and should not be used as a recommended default.

---

## 7. Recommended OpenStax Planning Stance

When planning tests with the OpenStax dataset, apply the following strict planning rules:

* **Planning Only**: Keep all OpenStax-related activities in the planning stage.
* **Use Tiny Subset**: Ensure any eventual plan targets only a small fraction of the dataset.
* **Prefer Balanced Preset**: Use the Balanced Synthetic-Validated Preset parameters.
* **Set Hard Provider-Call Cap**: Restrict the run with a low call ceiling.
* **Confirm Quota Headroom**: Verify provider API limits before any execution.
* **Define Stop Conditions**: Outline clear conditions to halt processing if issues arise.
* **No Execution**: Do not execute or run OpenStax jobs until explicitly approved.

---

## 8. Persistent Defaults

* **No Defaults Changed**: The persistent system defaults have not been changed.
* **Change Process**: Any alteration to runtime defaults requires a separate commit, a formal review, and fresh validation.
