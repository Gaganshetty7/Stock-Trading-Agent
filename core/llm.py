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
        base_llm=ChatGoogleGenerativeAI(
            model=_model,
            temperature=_temp,
            google_api_key=_api_key,
        )
       

        wrapped = AutoTrackingLLMWrapper(base_llm)
        return wrapped

    # elif LLM_PROVIDER == "anthropic":
    #     from langchain_anthropic import ChatAnthropic
    #     from config.settings import ANTHROPIC_API_KEY
    #     return ChatAnthropic(
    #         model=LLM_MODEL,
    #         temperature=LLM_TEMPERATURE,
    #         anthropic_api_key=ANTHROPIC_API_KEY,
    #     )

    # elif LLM_PROVIDER == "openai":
    #     from langchain_openai import ChatOpenAI
    #     from config.settings import OPENAI_API_KEY
    #     return ChatOpenAI(
    #         model=LLM_MODEL,
    #         temperature=LLM_TEMPERATURE,
    #         openai_api_key=OPENAI_API_KEY,
    #     )

    # else:
    #     raise ValueError(f"Unsupported LLM provider: {LLM_PROVIDER}")
