# -*- coding: utf-8 -*-
"""
ABG_agent 启动脚本
"""
import os
import sys
import uvicorn
from dotenv import load_dotenv

# 将当前目录加入 Python 搜索路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 加载配置
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def main():
    port = int(os.getenv("PORT", 9001))
    host = "0.0.0.0"
    
    print(f"🚀 ABG_agent (车BG 原生智能版) 正在启动...")
    print(f"   地址: http://{host}:{port}")
    print(f"   接口: http://{host}:{port}/chat")
    print(f"   配置: configs/car_fields.yaml")
    
    uvicorn.run("app.main:app", host=host, port=port, reload=True)

if __name__ == "__main__":
    main()
