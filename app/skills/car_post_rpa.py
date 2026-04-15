# -*- coding: utf-8 -*-
import asyncio
import os
import time
import re
from typing import Dict, Any, Optional, List
from playwright.async_api import async_playwright, Playwright, BrowserContext, Page

class CarPostSkill:
    """
    二手车/工程车发布原子技能 (RPA)。
    支持：文本表单填写、图片 HTTP 链接直接注入上传（无需本地文件 / 无 CORS 限制）。
    """
    def __init__(self):
        self.user_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../agent/user_data')
        os.makedirs(self.user_data_dir, exist_ok=True)
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        async with self._lock:
            if self.playwright is None:
                self.playwright = await async_playwright().start()
            if self.context is None:
                self.context = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=False,
                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
                )
                self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            return self.page

    async def close_browser(self):
        async with self._lock:
            if self.context: await self.context.close(); self.context = None
            if self.playwright: await self.playwright.stop(); self.playwright = None
            self.page = None

    def _convert_to_wan(self, value_str: str) -> str:
        if not value_str: return ""
        s = str(value_str).lower().replace(" ", "")
        try:
            nums = re.findall(r"[-+]?\d*\.\d+|\d+", s)
            if not nums: return ""
            val = float(nums[0])
            if "万" in s: return str(val)
            elif "k" in s or "千" in s: return str(val * 0.1)
            elif val >= 1000: return str(val / 10000)
            return str(val)
        except: return ""

    def _extract_numbers(self, value_str: str) -> str:
        if not value_str: return ""
        nums = re.findall(r"[-+]?\d*\.\d+|\d+", str(value_str))
        return nums[0] if nums else ""

    async def _capture_login_qr(self, page) -> Dict[str, str]:
        try: await page.click('text=扫码登录', timeout=5000)
        except: 
            try: await page.click('.login-item[data-type="qrcode"]', timeout=5000)
            except: pass
        await page.wait_for_selector('img.qrcode-img, img[alt="二维码"]', timeout=10000)
        qr_elem = await page.query_selector('img.qrcode-img, img[alt="二维码"]')
        qr_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../static/qrcodes')
        os.makedirs(qr_dir, exist_ok=True)
        qr_path = os.path.join(qr_dir, 'login_qr.png')
        await qr_elem.screenshot(path=qr_path)
        return {"status": "waiting_login", "image_path": "/static/qrcodes/login_qr.png"}

    async def _handle_login(self, page, qr_callback):
        if "post.58.com" not in page.url:
            await page.goto("https://post.58.com/che/9817/70185/s5", timeout=60000)
            await page.wait_for_load_state('networkidle')
        if await page.locator(".login-box").count() > 0 or "passport" in page.url:
            qr_result = await self._capture_login_qr(page)
            if qr_callback: qr_callback(qr_result)
            for _ in range(120):
                await asyncio.sleep(1)
                if await page.locator(".login-box").count() == 0 and "passport" not in page.url: break
            else: raise Exception("登录超时")

    async def _robust_js_click(self, page, text: str):
        """核心加固：精确匹配优先 + 仅命中可见元素 + 双发事件触发"""
        js_logic = """(text) => {
            const isVisible = (el) => {
                if (!el.offsetParent && el.style.display === 'none') return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const candidates = Array.from(document.querySelectorAll('li, span, a'))
                                   .filter(e => isVisible(e));
            // 优先精确匹配，防止数字如 "7" 命中 "2007" 等包含项
            let target = candidates.find(e => e.innerText.trim() === text);
            // 精确匹配无结果时再宽松匹配（长度限制更严）
            if (!target) {
                target = candidates.find(e => {
                    const t = e.innerText.trim();
                    return t.includes(text) && t.length <= text.length + 2;
                });
            }
            if (target) {
                target.scrollIntoView({ block: 'nearest' });
                target.click();
                ['mousedown', 'mouseup', 'click'].forEach(evtType => {
                    const ev = new MouseEvent(evtType, { bubbles: true, cancelable: true, view: window });
                    target.dispatchEvent(ev);
                });
                return true;
            }
            return false;
        }"""
        return await page.evaluate(js_logic, text)

    async def _perform_machine_type_selection(self, page, machine_type: str):
        print(f"➡️ 尝试解锁并选择机型: {machine_type}")
        sel = 'div.selectordef[name="objecttype"]'
        try:
            await page.click(sel, force=True, timeout=5000)
        except:
            await page.evaluate(f"document.querySelector('{sel}').click()")
        
        await asyncio.sleep(1.2)
        if await self._robust_js_click(page, machine_type):
            print(f"✅ 机型 [{machine_type}] 选中动作已下发")
        await asyncio.sleep(2)

    async def _fill_form_fields(self, page, info: Dict[str, Any]):
        print("📝 [串行校验模式] 填表启动...")
        
        # 1. 价格 & 新旧
        try:
            val_new = info.get("is_new") or "二手"
            await page.click(f'label:has-text("{"全新" if "全新" in val_new else "二手"}")', force=True)
        except: pass
        if info.get("price"):
            p = self._convert_to_wan(str(info.get("price")))
            if p: await page.fill("input#MinPrice", p, force=True)

        # 2. 小时数
        hs_val = info.get("dynamic_小时数") or info.get("xiaoshishu") or info.get("小时数")
        if hs_val:
            await page.fill("input#xiaoshishu", self._extract_numbers(str(hs_val)), force=True)
            await page.locator("input#xiaoshishu").blur()

        # 3. 严格串行：年份 -> 等待 -> 月份 (精确匹配数字)
        year = str(info.get("manufacture_year") or "")
        month = str(info.get("manufacture_month") or "")

        if year:
            y_sel = 'div.selectordef[name="chuchangnianxian"]'
            print(f"📅 [串行] 选择年份: {year}")
            await page.click(y_sel, force=True)
            await asyncio.sleep(0.5)
            await self._robust_js_click(page, year)
            
            # 等待确认填入
            for _ in range(10):
                txt = await page.locator(y_sel).inner_text()
                if year in txt: break
                await asyncio.sleep(0.5)
            
            # 用户要求：选完年份强制等 1 秒
            print("⏱️ 年份已锁定，等待 1 秒唤醒月份...")
            await asyncio.sleep(1.0)
        
        if month:
            m_sel = 'div.selectordef[name="shangpaiyuefen"]'
            # 关键修正：月份在列表里就是纯数字 "7"，不是 "7月"
            mo_val = str(int(month))
            print(f"📅 [串行] 选择月份数字: {mo_val}")
            try:
                # 等待月份下拉框进入可交互状态（年份选完后页面可能动态激活月份）
                await page.wait_for_selector(m_sel, state='visible', timeout=5000)
                await page.click(m_sel, force=True)
                # 等待月份下拉列表真正弹出（li 出现在下拉容器中）
                await asyncio.sleep(1.2)
                if await self._robust_js_click(page, mo_val):
                    print(f"✅ 月份 [{mo_val}] 选择指令已下发")
                    # DOM 回读确认：防止静默失败
                    await asyncio.sleep(0.5)
                    try:
                        txt = await page.locator(m_sel).inner_text()
                        if mo_val in txt:
                            print(f"✅ 月份 DOM 回读确认: {txt.strip()}")
                        else:
                            print(f"⚠️ 月份 DOM 回读异常，当前文本: {txt.strip()}，尝试重试...")
                            await page.click(m_sel, force=True)
                            await asyncio.sleep(0.8)
                            await self._robust_js_click(page, mo_val)
                            await asyncio.sleep(0.5)
                    except Exception as ve:
                        print(f"⚠️ 月份回读检查失败: {ve}")
                else:
                    print(f"❌ 未能在月份列表中找到数字: {mo_val}")
            except Exception as e:
                print(f"⚠️ 月份操作失败: {e}")

        # 4. 其他字段
        print("📝 处理剩余动态字段...")
        skipped = ["machine_type", "is_new", "manufacture_year", "manufacture_month", "price", "ad_slogan", "description", "other_details", "contact_name", "contact_phone", "xiaoshishu", "image_urls"]
        for fid, fval in info.items():
            if fid in skipped or not fval or "小时" in fid: continue
            
            print(f"➡️ 准备填充字段: {fid} = {fval}")
            
            # 尝试多种选择器：ID, Name
            input_sel = f"input#{fid}, input[name='{fid}'], .selectordef[id='{fid}'], .selectordef[name='{fid}']"
            
            # 如果常规选择器找不到，尝试通过 rows_wrap 的标题查找
            target_locator = page.locator(input_sel)
            if await target_locator.count() == 0:
                print(f"🔍 常规选择器未命中 [{fid}]，尝试获取 rows_title 匹配...")
                # 寻找包含该 fid（或者名称）的 rows_wrap
                js_find_sel = f"""(fid) => {{
                    const rows = Array.from(document.querySelectorAll('.rows_wrap'));
                    const targetRow = rows.find(r => {{
                        const input = r.querySelector('input, .selectordef');
                        return input && (input.id === fid || input.getAttribute('name') === fid);
                    }});
                    return targetRow ? (targetRow.querySelector('input') ? 'input' : '.selectordef') : null;
                }}"""
                found_tag = await page.evaluate(js_find_sel, fid)
                if found_tag:
                    target_locator = page.locator(f".rows_wrap:has(input[name='{fid}'], .selectordef[name='{fid}'], input[id='{fid}'], .selectordef[id='{fid}']) {found_tag}")
            
            if await target_locator.count() > 0:
                tag_name = await target_locator.evaluate("el => el.tagName")
                is_selectordef = await target_locator.evaluate("el => el.classList.contains('selectordef')")
                
                if is_selectordef:
                    print(f"👉 识别为选择器字段: {fid}")
                    await target_locator.click(force=True)
                    await asyncio.sleep(1.0)
                    if await self._robust_js_click(page, str(fval)):
                        print(f"✅ 字段 [{fid}] 已通过 JS 注入选择")
                    else:
                        print(f"⚠️ 字段 [{fid}] JS 点击未奏效，列表可能未弹出或值不存在")
                else:
                    print(f"👉 识别为输入框字段: {fid}")
                    is_num = any(x in fid.lower() for x in ["ton", "weight", "mile", "dun"])
                    await target_locator.fill(self._extract_numbers(str(fval)) if is_num else str(fval), force=True)
                    await target_locator.blur()
                    print(f"✅ 字段 [{fid}] 填充成功")
            else:
                print(f"❌ 无法在页面上定位到字段: {fid}")

        # 5. 描述与联系人
        try:
            title = (info.get("ad_slogan") or f"出售{info.get('machine_type', '设备')}")[:15]
            await page.fill("input#carname", title, force=True)
            await page.fill("textarea#Content", f"{info.get('description', '')}\n{info.get('other_details', '')}".strip()[:2000], force=True)
            if info.get("contact_name"): await page.fill("input#goblianxiren", info.get("contact_name"), force=True)
            if info.get("contact_phone"): await page.fill("input#Phone", info.get("contact_phone"), force=True)
        except: pass

        # 6. 图片上传
        image_urls = info.get("image_urls") or []
        if image_urls:
            await self._upload_images(page, image_urls)

    async def _upload_images(self, page, image_paths: List[str]):
        """
        图片上传：支持 HTTP/HTTPS 链接 和 本地文件路径混用。
        - HTTP 链接：通过 page.request.get 拉取为内存 buffer（走浏览器 Session，无 CORS 问题）
        - 本地路径：直接传路径字符串
        全部通过 set_input_files 注入到 58.com 的隐藏 file input，不需要点击弹窗。
        """
        # 58.com 图片上传区的 file input 选择器
        FILE_INPUT_SEL = "#imgUpload .html5 input[type='file']"
        MAX_IMAGES = 16

        # 过滤空值
        upload_inputs = [p for p in image_paths if isinstance(p, str) and p.strip()]
        if not upload_inputs:
            print("⚠️ 图片列表为空，跳过上传")
            return
        if len(upload_inputs) > MAX_IMAGES:
            print(f"⚠️ 图片数量 {len(upload_inputs)} 超过最大限制 {MAX_IMAGES}，截取前 {MAX_IMAGES} 张")
            upload_inputs = upload_inputs[:MAX_IMAGES]

        try:
            # 等待 file input 出现（页面可能异步渲染）
            await page.wait_for_selector(FILE_INPUT_SEL, timeout=8000)
        except Exception as e:
            print(f"❌ 未找到图片上传 input，跳过: {e}")
            return

        final_files = []
        for p in upload_inputs:
            if p.startswith("http://") or p.startswith("https://"):
                try:
                    # 用浏览器自身的 request 上下文下载，携带 Cookie/Session，天然无 CORS
                    response = await page.request.get(p, timeout=30000)
                    if response.ok:
                        filename = p.split("/")[-1].split("?")[0] or "image.jpg"
                        # 确保有正确的扩展名
                        if "." not in filename:
                            filename += ".jpg"
                        mime = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                        final_files.append({
                            "name": filename,
                            "mimeType": mime,
                            "buffer": await response.body()
                        })
                        print(f"✅ 图片下载成功: {p} → {filename} ({mime})")
                    else:
                        print(f"⚠️ 图片请求失败 [{response.status}]: {p}")
                except Exception as e:
                    print(f"⚠️ 图片下载异常: {p} — {e}")
            else:
                # 本地文件路径
                if os.path.isfile(p):
                    final_files.append(p)
                    print(f"✅ 本地图片已加入: {p}")
                else:
                    print(f"⚠️ 本地文件不存在，跳过: {p}")

        if not final_files:
            print("⚠️ 没有准备好有效的图片资源，跳过上传")
            return

        try:
            await page.locator(FILE_INPUT_SEL).set_input_files(final_files)
            print(f"📤 图片已注入 file input，共 {len(final_files)} 张，等待页面处理...")
            await asyncio.sleep(3)  # 等待前端上传逻辑触发和缩略图渲染
            print("✅ 图片上传步骤完成")
        except Exception as e:
            print(f"❌ set_input_files 失败: {e}")

    async def run(self, car_info: Dict[str, Any], mode: str = "fill", qr_callback=None) -> Dict[str, Any]:
        try:
            page = await self._ensure_browser()
            await self._handle_login(page, qr_callback)
            if "che/9817/70185" not in page.url: await page.goto("https://post.58.com/che/9817/70185/s5", timeout=30000)
            await self._perform_machine_type_selection(page, car_info.get("machine_type"))
            if mode == "discover":
                fields = await self._detect_dynamic_fields(page)
                return {"status": "success", "mode": "discover", "dynamic_fields": fields}
            await self._fill_form_fields(page, car_info)
            return {"status": "success", "mode": "fill"}
        except Exception as e:
            print(f"❌ RPA 失败: {e}"); return {"status": "error", "message": str(e)}

    async def _detect_dynamic_fields(self, page) -> List[Dict[str, str]]:
        script = """() => {
            const rows = Array.from(document.querySelectorAll('#postForm .rows_wrap'));
            let start = false; const dynamic = [];
            for (const row of rows) {
                const titleEl = row.querySelector('.rows_title');
                if (!titleEl || row.style.display === 'none') continue;
                const title = titleEl.innerText.trim().replace('*', '');
                if (title === '机型') { start = true; continue; }
                if (['出厂年限', '出厂年份'].includes(title)) { break; }
                if (start && title) {
                    const input = row.querySelector('input, .selectordef');
                    dynamic.push({ name: title, id: input ? (input.id || input.getAttribute('name')) : 'dynamic_'+title });
                }
            }
            return dynamic;
        }"""
        found = await page.evaluate(script); results = []
        for f in found: results.append({"id": f['id'], "name": f['name'], "description": f"请输入{f['name']}"})
        return results

car_post_skill = CarPostSkill()
