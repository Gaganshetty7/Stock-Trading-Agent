import time
from typing import Any, Optional

# Langchain callbacks to intercept the exact LLM generation
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from .helpers.context import context_used_pct
from .helpers.detector import detect_caller
from .helpers.models import CallRecord
from .helpers.storage import append_call

from core.logger import get_logger

logger = get_logger("usage_tracker", console_output=False, shared_log=False)


# ─────────────────────────────────────────────
# INTERNAL CALLBACK TO CAPTURE RAW GENERATIONS
# ─────────────────────────────────────────────
class TokenCaptureCallback(BaseCallbackHandler):
    """Intercepts raw LLM outputs before LCEL parsers strip usage metadata."""
    def __init__(self):
        self.last_response = None

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            if response.generations and response.generations[0]:
                # Grab the actual generation message (contains usage_metadata)
                self.last_response = response.generations[0][0].message
        except Exception:
            pass


# ─────────────────────────────────────────────
# TOKEN EXTRACTION (Robust Pathing)
# ─────────────────────────────────────────────
def _extract_tokens(response: Any) -> tuple[int, int, int]:
    u = {}

    if hasattr(response, "usage_metadata") and response.usage_metadata:
        u = dict(response.usage_metadata)
    elif hasattr(response, "response_metadata") and response.response_metadata:
        rm = response.response_metadata
        if isinstance(rm, dict):
            u = rm.get("usage") or rm.get("token_usage") or rm
    elif hasattr(response, "additional_kwargs"):
        ak = response.additional_kwargs or {}
        if isinstance(ak, dict):
            u = ak.get("usage", ak)
    elif isinstance(response, dict):
        u = response.get("usage") or response.get("usage_metadata") or response

    inp = int(u.get("input_tokens") or u.get("prompt_tokens") or 0)
    out = int(u.get("output_tokens") or u.get("completion_tokens") or 0)
    total = int(u.get("total_tokens") or (inp + out))

    return inp, out, total


# ─────────────────────────────────────────────
# MODEL EXTRACTION
# ─────────────────────────────────────────────
def _extract_model(llm: Any) -> str:
    if hasattr(llm, "_llm"):
        return _extract_model(llm._llm)
        
    if llm.__class__.__name__ == "RunnableSequence" and hasattr(llm, "steps"):
        for step in llm.steps:
            model_name = _extract_model(step)
            if model_name != "RunnableSequence" and not model_name.startswith("Runnable"):
                return model_name

    if hasattr(llm, "bound"):
        return _extract_model(llm.bound)

    for attr in ("model", "model_name", "_model_name", "model_id"):
        v = getattr(llm, attr, None)
        if isinstance(v, str) and v:
            return v
            
    return llm.__class__.__name__


# ─────────────────────────────────────────────
# WRAPPER (WITH INJECTED RUNTIME CALLBACKS)
# ─────────────────────────────────────────────
class AutoTrackingLLMWrapper:

    def __init__(self, llm: Any, run_id: Optional[str] = None):
        self._llm = llm
        self.run_id = run_id
        self.model = _extract_model(llm)

    def _wrap(self, obj):
        if isinstance(obj, AutoTrackingLLMWrapper):
            return obj
        if hasattr(obj, "invoke") or hasattr(obj, "ainvoke") or hasattr(obj, "stream"):
            return AutoTrackingLLMWrapper(obj)
        return obj

    def _inject_callback(self, config: Any) -> tuple[Any, TokenCaptureCallback]:
        """Injects our callback securely into LangChain's config block."""
        cb = TokenCaptureCallback()
        if config is None:
            config = {"callbacks": [cb]}
        elif isinstance(config, dict):
            config = config.copy()
            if "callbacks" in config:
                if isinstance(config["callbacks"], list):
                    config["callbacks"].append(cb)
                else:
                    config["callbacks"] = [config["callbacks"], cb]
            else:
                config["callbacks"] = [cb]
        return config, cb

    # ─────────────────────────────
    def invoke(self, input: Any, config: Any = None, **kwargs: Any):
        start = time.time()
        config, cb = self._inject_callback(config)
        try:
            res = self._llm.invoke(input, config=config, **kwargs)
            
            # If the parser stripped usage data, recover it from our execution hook
            final_res = res if cb.last_response is None else cb.last_response
            
            if self.model == "RunnableSequence" or self.model.startswith("Runnable"):
                self.model = _extract_model(self._llm)
                
            self._log(final_res, time.time() - start, "SUCCESS")
            return res
        except Exception as e:
            self._log_error(e, time.time() - start)
            raise

    # ─────────────────────────────
    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any):
        start = time.time()
        config, cb = self._inject_callback(config)
        try:
            res = await self._llm.ainvoke(input, config=config, **kwargs)
            
            final_res = res if cb.last_response is None else cb.last_response
            
            if self.model == "RunnableSequence" or self.model.startswith("Runnable"):
                self.model = _extract_model(self._llm)
                
            self._log(final_res, time.time() - start, "SUCCESS")
            return res
        except Exception as e:
            self._log_error(e, time.time() - start)
            raise

    # ─────────────────────────────
    def stream(self, *args, **kwargs):
        start = time.time()
        try:
            stream = self._llm.stream(*args, **kwargs)

            def gen():
                for c in stream:
                    yield c
                self._log({}, time.time() - start, "SUCCESS")

            return gen()
        except Exception as e:
            self._log_error(e, time.time() - start)
            raise

    # ─────────────────────────────
    def batch(self, *args, **kwargs):
        start = time.time()
        try:
            res = self._llm.batch(*args, **kwargs)
            for r in res:
                self._log(r, 0.0, "SUCCESS")
            return res
        except Exception as e:
            self._log_error(e, time.time() - start)
            raise

    # ─────────────────────────────
    def with_structured_output(self, schema: Any, **kwargs: Any):
        wrapped = self._llm.with_structured_output(schema, **kwargs)
        return AutoTrackingLLMWrapper(wrapped)

    # ─────────────────────────────
    def __getattr__(self, name: str):
        attr = getattr(self._llm, name)
        return self._wrap(attr)

    def __or__(self, other):
        return self._wrap(self._llm.__or__(other))

    def __ror__(self, other):
        return self._wrap(self._llm.__ror__(other))

    # ─────────────────────────────
    def _build_record(self):
        component, worker, _ = detect_caller()
        return CallRecord(
            component=component,
            worker_name=worker,
            model=self.model,
        )

    # ─────────────────────────────
    def _log(self, response: Any, duration: float, status: str):
        record = self._build_record()
        record.status = status
        record.duration_seconds = round(duration, 2)

        inp, out, total = _extract_tokens(response)

        record.input_tokens = inp
        record.output_tokens = out
        record.total_tokens = total

        record.context_limit, record.context_window_used_pct = context_used_pct(
            record.model, total
        )

        # Log to core logger
        logger.info(
            f"LLM Call: {record.model} | Status: {status} | "
            f"Tokens: {total} | Context: {total}/{record.context_limit} ({record.context_window_used_pct}%) | "
            f"Duration: {record.duration_seconds}s"
        )

        append_call(record)

    def _log_error(self, exc: Exception, duration: float):
        record = self._build_record()
        record.status = "FAILED"
        record.duration_seconds = round(duration, 2)
        
        # Log to core logger
        logger.error(f"LLM Call Failed: {self.model} | Duration: {round(duration, 2)}s | Error: {str(exc)}")
        
        append_call(record)
