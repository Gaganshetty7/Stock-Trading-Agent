from langchain_core.language_models import BaseChatModel
from config.settings import LLM_PROVIDER, LLM_MODEL, LLM_TEMPERATURE
from usage_tracker import AutoTrackingLLMWrapper

def get_llm(
    provider: str | None = None,
    temperature: float | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> BaseChatModel:
    
    _provider = provider if provider is not None else LLM_PROVIDER
    _model = model if model is not None else LLM_MODEL
    _temp = temperature if temperature is not None else LLM_TEMPERATURE
    
    if _provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        from config.settings import GEMINI_API_KEY
        _api_key = api_key if api_key is not None else GEMINI_API_KEY
        kwargs = {"model": _model, "temperature": _temp, "google_api_key": _api_key}
        base_llm = ChatGoogleGenerativeAI(**kwargs)

    # elif _provider == "anthropic":
    #     from langchain_anthropic import ChatAnthropic
    #     from config.settings import ANTHROPIC_API_KEY
    #     _api_key = api_key if api_key is not None else ANTHROPIC_API_KEY
    #     kwargs = {"model": _model, "temperature": _temp, "api_key": _api_key}
    #     base_llm = ChatAnthropic(**kwargs)

    elif _provider == "openai":
        from langchain_openai import ChatOpenAI
        from config.settings import OPENAI_API_KEY
        _api_key = api_key if api_key is not None else OPENAI_API_KEY
        kwargs = {"model": _model, "temperature": _temp, "openai_api_key": _api_key}
        base_llm = ChatOpenAI(**kwargs)

    else:
        raise ValueError(f"Unsupported LLM provider: {_provider}")

    # Centralized usage tracking wrapper
    return AutoTrackingLLMWrapper(base_llm)
