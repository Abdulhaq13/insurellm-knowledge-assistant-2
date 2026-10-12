"""Hard spending cap for paid (OpenAI) calls made during evals.

Every LLM call made by the pipeline under test is wrapped: its real cost (litellm.completion_cost)
is added to a ledger file that persists across runs and --resume, and once the ledger reaches the
cap no further paid call is allowed. Free providers (Groq, local models) are not counted.
"""
import json
import sys
import threading
from pathlib import Path

import litellm

LEDGER = Path(__file__).parent / "results" / "openai_spend.json"
PAID_PROVIDERS = {"openai"}
# Default cap on the ledger total (all eval runs together), below the ~$2 OpenAI credit.
# The ledger doesn't see app/CLI questions, so real spend is a little higher than it shows.
DEFAULT_CAP_USD = 1.50
_lock = threading.Lock()


class BudgetExceeded(Exception):
    pass


class Budget:
    def __init__(self, cap_usd: float, label: str, ledger: Path = LEDGER):
        self.cap = cap_usd
        self.label = label
        self.ledger = ledger
        self.data = json.loads(ledger.read_text(encoding="utf-8")) if ledger.exists() else {
            "total_usd": 0.0, "calls": 0, "by_label": {}
        }

    @property
    def total(self) -> float:
        return self.data["total_usd"]

    def check(self):
        if self.total >= self.cap:
            raise BudgetExceeded(f"OpenAI spend ${self.total:.4f} reached the ${self.cap:.2f} cap")

    def record(self, cost: float):
        with _lock:
            self.data["total_usd"] = round(self.total + cost, 6)
            self.data["calls"] += 1
            self.data["by_label"][self.label] = round(self.data["by_label"].get(self.label, 0.0) + cost, 6)
            self.ledger.parent.mkdir(exist_ok=True)
            self.ledger.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def wrap(self, completion):
        def tracked(*args, **kwargs):
            model = kwargs.get("model") or (args[0] if args else "")
            try:
                provider = litellm.get_llm_provider(model)[1]
            except Exception:
                provider = None
            if provider not in PAID_PROVIDERS:
                return completion(*args, **kwargs)
            if kwargs.get("stream"):
                raise BudgetExceeded("streaming calls can't be cost-tracked; evals don't stream")
            self.check()
            response = completion(*args, **kwargs)
            self.record(litellm.completion_cost(completion_response=response))
            return response

        return tracked

    def install(self, package_prefixes: tuple[str, ...]):
        """Replace `completion` in every loaded module of the given packages with the tracked one."""
        for name, module in list(sys.modules.items()):
            if name.split(".")[0] in package_prefixes and getattr(module, "completion", None) is litellm.completion:
                module.completion = self.wrap(litellm.completion)
