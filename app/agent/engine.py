# -*- coding: utf-8 -*-
import json
import yaml
import os
import asyncio
import httpx
import re
from typing import List, Dict, Any, Optional

class NativeAgentEngine:
    """
    原生 Agent 引擎 (品类无关版)。
    使用双路架构 (Sequential Extraction -> Chat) 解决大模型 JSON 输出不稳定或夹杂推理过程的问题。
    """
    def __init__(self, api_key: str, base_url: str, model: str = "chatling-mini", config_file: str = "configs/engineering_vehicle_fields.yaml"):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = 60.0
        
        # 加载品类配置文件
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), config_file)
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            self.fields = self.config.get("fields", [])

    def _get_extract_prompt(self, collected_info: Dict[str, Any], dynamic_fields: Optional[List[Dict[str, Any]]] = None) -> str:
        """构建提取提示词 - 专注于纯 JSON 输出，零温度"""
        base_fields = [
            f"- **{f['id']}** ({f['name']}): {f['description']}"
            for f in self.fields if not f.get('internal')
        ]
        
        if dynamic_fields:
            for df in dynamic_fields:
                base_fields.append(f"- **{df['id']}** ({df['name']}): {df['description']} (动态探测)")
        
        all_fields_str = "\n".join(base_fields)
        collected_str = json.dumps(collected_info, ensure_ascii=False, indent=2)

        prompt = f"""你是一个后台信息提取模块，没有人类感情，只需遵循严格的 JSON 格式输出。
任务：根据给定的"已收集信息"和用户的"最新回复"，提取出新的相关发帖字段信息或用户明确的发布意愿。

## 目标提取字段定义：
{all_fields_str}

## 特别说明——图片字段 (image_urls)：
1. 该字段由后端系统自动通过正则表达式提取 URL，你不需要解析 URL 链接。
2. **严禁脑补**：如果 collected_info["image_urls"] 是空列表 []，即使报文中用户说“发图片了”，你也必须认定图片【尚未采集】。
3. **重点关注意图**：如果用户说“发完了”、“就这些了”，意味着图片收集结束，将 intent_to_publish 判定为 True。

## 极度重要——已有字段的覆盖保护规则：
1. 对于已存在值的字段，只有在用户明确针对该字段提出修改时（如“价格改成5万”），才允许覆盖。
2. 绝对禁止因为用户消息中偶然出现了某个数字（例如：年份或小时数），就贸然覆盖已有字段。必须确认是针对该字段的动作。

## 当前已收集的信息（作为增量提取的基准）：
{collected_str}

## 特别注意——纠正与覆盖逻辑：
用户在对话中随时可能纠正或修改之前的信息（例如：把价格从3万改成5万、联系人说错了等）。
当用户有明确修改意图时（如"价格改成5万"、"不对，是王先生"、"电话换成xxx"等），
你必须将修改后的新值放入 extracted_info 对应字段，新值将覆盖旧值。不要忽略用户的纠正！
若信息有更新，也请重新生成 ad_slogan 和 description。

判断标准：用户如果没有明确说"出厂年限改成xxx"或"不对年份应该是xxx"，就不要动已有字段的值。

## 输出要求（极度重要）：
你只能、必须输出纯正的 JSON 字符串（无需任何 Markdown 标记或解析说明，绝对不要有推理或分析文字），返回的 JSON 必须具有以下严格结构。如果没有得到相关的信息，就不要放进去。
{{
  "extracted_info": {{
     "提取到的对应字段名": "对应的值"
  }},
  "ad_slogan": "你自动生成的短广告语（绝对禁止超过15个字！不要包含字段名称，只输出内容）",
  "description": "你自动生成的长说明（直接输出描述正文，绝对禁止以'补充说明'、'描述'等字眼开头或结尾）",
  "intent_to_publish": false // 只有用户明确表示"确认发布"、"没问题"等肯定的发布意图时才为 true
}}
"""
        return prompt

    def _get_chat_prompt(self, collected_info: Dict[str, Any], dynamic_fields: Optional[List[Dict[str, Any]]] = None) -> str:
        """构建系统提示词 - 仅负责对话表现"""
        required_fields = [f for f in (self.fields or []) if f.get("required") and not f.get("internal")]
        missing_names = []
        for f in required_fields:
            v = collected_info.get(f.get("id", ""))
            if not v or (isinstance(v, str) and not v.strip()):
                missing_names.append(f.get("name") or f.get("id"))
                
        if dynamic_fields:
            for df in dynamic_fields:
                v = collected_info.get(df.get("id", ""))
                if not v or (isinstance(v, str) and not v.strip()):
                    missing_names.append(df.get("name") or df.get("id"))
        
        missing_str = ", ".join(missing_names) if missing_names else "无（已收集全部所需的核心信息）"
        
        prompt = f"""你是一个负责收集发帖信息的智能车服接待员。
你的任务是：像人类一样与用户自然对话，通过闲聊逐步收集到发布所需的必填信息。系统已经自动在后台提取了用户刚刚提供的信息，因此你只用专注于下一步该怎么跟用户聊。



## 当前信息状态：
- 🚨 尚未收集的核心必填字段有：{missing_str}

## 你的行为守则（负责生成文字对话给用户看）：
2. **追问缺失项**：观察上方的 `尚未收集的核心必填字段`。
   - 极简原则：只问最关键的、能让帖子成功发布的项。
   - 关于 internal/辅助项：标记为 `internal` 的字段（如其他细节）绝对禁止主动提问，只用于静默存储。
   - 关于动态探测字段：如果 RPA 探测到了像“地址”、“微信号”之类不影响发布大局的动态项，尽量一句话带过（如“最后再补充下位置就行”），或者不再死板地逐个编号索要。
3. 关于图片的具体要求：
   - 图片作为基础信息阶段的最后一项提问。
   - 没图时：请亲切地引导用户发图。
   - 有图时：报出当前已收到的数量。
   - 绝对红线：只要 `image_urls` 还是空的，绝对禁止发送任何包含“信息已全部收齐”、“请核对”或“即将发布”字样的内容！
4. 格式要求：提问必须使用“1）、2）”编号并独占一行。核心词用方括号。并在核心关键词上使用方括号'【】'包围，拒绝使用Markdown的**字符。

规范的排版格式如下：
如果问两个问题：
1）您的预期【价格】大概是多少万元嘞？
2）方便留一下【联系人】姓名吗？
如果只问一个问题：
请问这台机器的【出厂年份】和【月份】具体是多少呢？

"""
        return prompt

    async def _fetch(self, messages: List[Dict[str, Any]], temperature: float) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False
        }
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
            if data and data.get("choices"):
                return data["choices"][0].get("message", {}).get("content", "").strip()
            if "message" in data:
                raise Exception(f"API Error: {data.get('message')} - {data.get('code')}")
            raise Exception(f"Unexpected response: {data}")

    def _parse_extracted_json(self, text: str) -> Dict[str, Any]:
        t = text.strip()
        if "```json" in t:
            t = t.split("```json")[-1].split("```")[0].strip()
        elif "```" in t:
            t = t.split("```")[-1].split("```")[0].strip()
        try:
            m = re.search(r"\{[\s\S]*\}", t)
            if m:
                return json.loads(m.group(0))
            return json.loads(t)
        except Exception:
            return {}

    async def chat(self, user_input: str, history: List[Dict[str, str]], collected_info: Dict[str, Any], dynamic_fields: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        进行双路处理：
        1. 提取用户的输入增量信息
        2. 基于更新后的信息做出回复
        """
        import random

        def _build_fallback_reply(current_info: Dict[str, Any]) -> str:
            required_fields = [f for f in (self.fields or []) if f.get("required") and not f.get("internal")]
            missing = []
            for f in required_fields:
                v = current_info.get(f.get("id"))
                if not v or (isinstance(v, str) and not v.strip()):
                    missing.append(f.get("name") or f.get("id"))
            if not missing:
                return "您提供的信息已齐全，是否立即为您执行自动发布？"
            target = missing[0]
            return f"好的，收到。不过还需要再麻烦您提供一下【{target}】是怎样的？"

        updated_info = collected_info.copy()
        extracted_info = {}
        intent_to_publish = False

        # --- 阶段 1: 提取 ---
        extract_history = []
        for msg in history[-4:]:
            extract_history.append(msg)
        extract_history.append({"role": "user", "content": user_input})
        
        extract_messages = [{"role": "system", "content": self._get_extract_prompt(collected_info, dynamic_fields)}] + extract_history

        try:
            extract_text = await self._fetch(extract_messages, temperature=0.1)
            if extract_text:
                parsed = self._parse_extracted_json(extract_text)
                if isinstance(parsed, dict):
                    ext = parsed.get("extracted_info", {})
                    if isinstance(ext, dict):
                        # 核心修改：动态将 RPA 探测到的字段 ID 加入白名单，允许提取
                        valid_keys = {f.get("id") for f in (self.fields or []) if f.get("id")}
                        valid_keys.add("other_details")
                        if dynamic_fields:
                            for df in dynamic_fields:
                                valid_keys.add(df.get("id"))
                        
                        ext = {k: v for k, v in ext.items() if k in valid_keys}
                        extracted_info.update(ext)
                    
                    if parsed.get("ad_slogan"):
                        extracted_info["ad_slogan"] = parsed["ad_slogan"]
                    if parsed.get("description"):
                        extracted_info["description"] = parsed["description"]
                        
                    is_publish = parsed.get("intent_to_publish", False)
                    if isinstance(is_publish, str):
                        intent_to_publish = is_publish.lower() == "true"
                    else:
                        intent_to_publish = bool(is_publish)
        except Exception as e:
            print(f"Error in extraction phase: {type(e).__name__}: {e}")

        updated_info.update(extracted_info)

        # 硬性规则兜底确认发布意图：大模型常常漏提取 intent
        required_fields = [f for f in (self.fields or []) if f.get("required") and not f.get("internal")]
        missing_for_publish = []
        for f in required_fields:
            v = updated_info.get(f.get("id"))
            if not v or (isinstance(v, str) and not v.strip()):
                missing_for_publish.append(f.get("name") or f.get("id"))
        
        # 增加对动态探测字段的校验
        if dynamic_fields:
            for df in dynamic_fields:
                v = updated_info.get(df.get("id"))
                if not v or (isinstance(v, str) and not v.strip()):
                    missing_for_publish.append(df.get("name") or df.get("id"))
                
        if not missing_for_publish:
            # 严格拦截意图，防止大模型抽风自动跳过确认
            clean_input = user_input.strip().lower()
            is_confirm = False
            
            # 1. 硬匹配常见的肯定词典
            if clean_input in ["好", "行", "可以", "是", "对", "ok", "ok的", "没问题", "发吧", "去发布", "确认", "发布", "确认发布", "上架", "去发", "嗯", "嗯嗯", "嗯嗯嗯", "就发吧", "就这样", "没毛病"]:
                is_confirm = True
            for w in ["发布", "确认", "没问题", "上架", "去发", "执行", "可以提交"]:
                if w in clean_input and len(clean_input) < 15: # 防超长误判
                    is_confirm = True
            
            # 2. 判断上下文状态：机器人上一轮是否刚刚弹出了“确认列表”？
            last_bot_msg = next((msg["content"] for msg in reversed(history) if msg["role"] == "assistant"), "")
            is_confirming_state = "请您最后核对即将发布的贴文信息" in last_bot_msg or "确认无误" in last_bot_msg
            
            # 如果正在确认中...
            if is_confirming_state:
                # 过滤掉每次都会生成的广告语和描述
                real_updates = {k: v for k, v in extracted_info.items() if k not in ["ad_slogan", "description"]}
                
                # 如果用户的话非常简短且命中了确认词，直接当做确认发布
                if is_confirm and len(clean_input) <= 6:
                    is_confirm = True
                    intent_to_publish = True
                # 如果有实质性的信息被提取到，说明用户在纠正信息，应重新展示列表
                elif real_updates:
                    is_confirm = False
                    intent_to_publish = False
                # 若大模型正确读出了同意意图，直接放行
                elif intent_to_publish:
                    is_confirm = True
                # 若用户只是回了一句简短词，且没有提取到新信息，默认在同意
                elif len(clean_input) <= 6:
                    is_confirm = True
            else:
                # 如果还没展示过确认列表（初次收满信息），强行忽视大模型可能产生的 intent 幻觉
                if not is_confirm:
                    intent_to_publish = False
                    
            if not is_confirm and not intent_to_publish:
                # 生成给用户的确认列表
                order_ids = [
                    "machine_type", "is_new", "manufacture_year", "manufacture_month", "price", 
                    "ad_slogan", "description", "other_details", 
                    "contact_name", "contact_phone"
                ]
                lines = ["信息已全部收齐！请您最后核对即将发布的贴文信息：\n"]
                for f_id in order_ids:
                    f_name = next((f.get("name") for f in self.fields if f.get("id") == f_id), f_id)
                    val = updated_info.get(f_id, "无")
                    if not val: val = "无"
                    lines.append(f"- 【{f_name}】: {val}")
                
                lines.append("\n确认无误的话，我就可以为您提交了。若有修改，也请直接告诉我。")
                
                return {
                    "content": "\n".join(lines),
                    "updated_collected_info": updated_info,
                    "intent_to_publish": False
                }
            else:
                return {
                    "content": "好的，收到您的确认指令，紧锣密鼓为您执行发布操作！",
                    "updated_collected_info": updated_info,
                    "intent_to_publish": True
                }

        # --- 阶段 2: 闲聊回复 ---
        chat_messages = [{"role": "system", "content": self._get_chat_prompt(updated_info, dynamic_fields)}]
        for msg in history[-6:]:
            chat_messages.append(msg)
        chat_messages.append({"role": "user", "content": user_input})

        try:
            reply_text = await self._fetch(chat_messages, temperature=0.4)
            # 净化清理，防万一
            reply_text = re.sub(r"```json[\s\S]*?```", "", reply_text, flags=re.IGNORECASE).strip()
            if "{" in reply_text and "extracted_info" in reply_text:
                reply_text = reply_text.split("{")[0].strip()

            if not reply_text:
                reply_text = _build_fallback_reply(updated_info)
                
            return {
                "content": reply_text,
                "updated_collected_info": updated_info,
                "intent_to_publish": intent_to_publish
            }

        except Exception as e:
            print(f"Error in chat phase: {type(e).__name__}: {e}")
            return {
                "content": _build_fallback_reply(updated_info),
                "updated_collected_info": updated_info,
                "intent_to_publish": intent_to_publish
            }
