from langchain_core.language_models import BaseChatModel
from config.settings import LLM_PROVIDER, LLM_MODEL, LLM_TEMPERATURE


def get_llm() -> BaseChatModel:
    if LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        from config.settings import GEMINI_API_KEY
        return ChatGoogleGenerativeAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            google_api_key=GEMINI_API_KEY,
        )

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
