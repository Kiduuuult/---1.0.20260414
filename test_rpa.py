# -*- coding: utf-8 -*-
import asyncio
import json
import os
import sys

# 确保能找到 app 目录
sys.path.append(os.getcwd())

from app.skills.car_post_rpa import car_post_skill

async def main():
    # 用户提供的测试参数
    car_info = {
        'machine_type': '装载机', 
        'is_new': '全新', 
        'manufacture_date': '2023年3月', 
        'price': '3', 
        'ad_slogan': '全新2023装载机出售', 
        'description': '这是一台2023年3月出厂的全新装载机，目前以3万元的价格转让。车辆保养状况良好，配置齐全，适合需要高效运输或施工的用户。欢迎有意者详询。', 
        'other_details': '', 
        'contact_name': '王女士', 
        'contact_phone': '12312341234'
    }
    
    print("🚀 启动 RPA 填充测试...")
    print(f"📦 测试数据: {json.dumps(car_info, ensure_ascii=False, indent=2)}")
    
    # 执行填充模式 (mode="fill")
    # 如果你想测试探测模式，可以改为 mode="discover"
    result = await car_post_skill.run(car_info, mode="fill")
    
    print("\n" + "="*30)
    print(f"🏁 测试结果: {result}")
    print("="*30)

if __name__ == "__main__":
    asyncio.run(main())
