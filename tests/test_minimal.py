# -*- coding: utf-8 -*-
import asyncio
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

async def test_minimal():
    load_dotenv()
    chat = ChatOpenAI(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        model=os.getenv("LLM_MODEL", "chatling-mini")
    )
    print("DEBUG: Sending minimal message...")
    try:
        res = await chat.invoke([HumanMessage(content="Hello")])
        print(f"DEBUG: Success! Response: {res.content}")
    except Exception as e:
        print(f"DEBUG: Failed! Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_minimal())
