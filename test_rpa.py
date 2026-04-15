# -*- coding: utf-8 -*-
import asyncio
import json
import os
import sys

# 确保能找到 app 目录
sys.path.append(os.getcwd())

from app.skills.car_post_rpa import car_post_skill

async def main():
    # 用户提供的测试参数（含图片 HTTP 链接，测试图片上传功能）
    car_info = {
        'machine_type': '装载机',
        'is_new': '全新',
        'manufacture_year': '2023',
        'manufacture_month': '3',
        'price': '3',
        'ad_slogan': '全新2023装载机出售',
        'description': '这是一台2023年3月出厂的全新装载机，目前以3万元的价格转让。车辆保养状况良好，配置齐全，适合需要高效运输或施工的用户。欢迎有意者详询。',
        'other_details': '',
        'contact_name': '王女士',
        'contact_phone': '12312341234',
        # 🆕 图片链接（HTTP URL），RPA 会通过 page.request.get 下载后直接注入 file input
        'image_urls': [
            'https://pic4.58cdn.com.cn/nowater/lbgfe/image/n_v3b1b0169923bf4701ac80aabda561f523.jpg', 
            'https://pic4.58cdn.com.cn/nowater/lbgfe/image/n_v3a24af727b39c4c5d87b3f033189ac57c.jpg', 
        ]
    }
    
    print("🚀 启动 RPA 填充测试（含图片上传）...")
    print(f"📦 测试数据: {json.dumps(car_info, ensure_ascii=False, indent=2)}")
    
    # 执行填充模式 (mode="fill")
    result = await car_post_skill.run(car_info, mode="fill")
    
    print("\n" + "="*30)
    print(f"🏁 测试结果: {result}")
    print("="*30)

if __name__ == "__main__":
    asyncio.run(main())
