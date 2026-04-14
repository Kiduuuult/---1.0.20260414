# -*- coding: utf-8 -*-
import asyncio
import os
import sys
from dotenv import load_dotenv

# 将项目根目录加入路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.engine import NativeAgentEngine

async def test_engine_extraction():
    load_dotenv()
    
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL", "chatling-mini")
    
    if not api_key:
        print("❌ 请在 .env 中配置 LLM_API_KEY")
        return

    engine = NativeAgentEngine(
        api_key=api_key,
        base_url=base_url,
        model=model,
        config_file="configs/engineering_vehicle_fields.yaml"
    )

    # 模拟一段对话
    session_info = {
        "history": [],
        "collected_info": {}
    }

    test_inputs = [
        "我想卖一台挖掘机",
        "是2021年的三一重工，二手的，打算卖15.5万",
        "标题就叫‘精品三一挖掘机转让’吧，描述是‘车况很好，一直自己在开’",
        "我姓王，电话是18001841234"
    ]

    print(f"🚀 开始测试原生引擎提取 (品类: 工程车)...")
    
    for user_msg in test_inputs:
        print(f"\n👤 用户: {user_msg}")
        result = await engine.chat(
            user_input=user_msg,
            history=session_info["history"],
            collected_info=session_info["collected_info"]
        )
        
        # 更新状态
        session_info["history"].append({"role": "user", "content": user_msg})
        session_info["history"].append({"role": "assistant", "content": result["content"]})
        session_info["collected_info"] = result["updated_collected_info"]
        
        print(f"🤖 Agent: {result['content']}")
        print(f"📊 当前收集到的信息: {session_info['collected_info']}")

if __name__ == "__main__":
    asyncio.run(test_engine_extraction())
