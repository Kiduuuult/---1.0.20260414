import asyncio
import os
from playwright.async_api import async_playwright

async def main():
    user_data_dir = os.path.join(os.getcwd(), 'app/agent/user_data')
    print(f"Using user_data_dir: {user_data_dir}")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            args=["--start-maximized"]
        )
        page = await context.new_page()
        try:
            print("Navigating to https://post.58.com/che/9817/70185/s5...")
            await page.goto("https://post.58.com/che/9817/70185/s5", timeout=60000)
            await page.wait_for_load_state('networkidle')
            
            # Hide ads/popups
            await page.evaluate("""() => {
                document.querySelectorAll('.popup_home, [id*="pop"], .dialog-wrap, .guide-wrap').forEach(el => {
                    try { el.style.display = 'none'; } catch(e) {}
                });
            }""")
            
            if "passport" in page.url or await page.locator(".login-box").count() > 0:
                print("NOT LOGGED IN! Please login from the web UI first.")
                await context.close()
                return

            # 提前定义好提取脚本
            script = """
            () => {
                const results = [];
                document.querySelectorAll('div.rows_wrap:not([style*="display: none"]) input[type="inputText"], div.rows_wrap:not([style*="display: none"]) input.inputText').forEach(el => {
                    const row = el.closest('.rows_wrap');
                    let labelStr = row ? row.querySelector('.rows_title')?.innerText.trim() : '';
                    if (labelStr) {
                         results.push({ label: labelStr, type: 'input', id: el.id, name: el.name });
                    }
                });
                document.querySelectorAll('div.rows_wrap:not([style*="display: none"]) div.selectordef').forEach(el => {
                    const row = el.closest('.rows_wrap');
                    let labelStr = row ? row.querySelector('.rows_title')?.innerText.trim() : '';
                    // 获取备选项，看看是不是下拉
                    let text = el.innerText.trim().replace(/\\n/g, '');
                    if (labelStr) {
                         results.push({ label: labelStr, type: 'dropdown', class: el.className, name: el.getAttribute('name'), current_text: text });
                    }
                });
                return results;
            }
            """

            machine_types = ['挖掘机', '装载机', '起重机', '压路机', '叉车', '油罐车']
            
            for mt in machine_types:
                try:
                    print(f"\\n--- Testing Machine Type: {mt} ---")
                    
                    # 重新触发机型下拉 (如果已经是选择状态，点击它重新开启面板)
                    if await page.locator('div.selectordef[name="objecttype"]').count() > 0:
                        await page.click('div.selectordef[name="objecttype"]', force=True, timeout=3000)
                        await asyncio.sleep(1)
                    
                    # 使用 JS 击穿点击该机型
                    js_click_script = """(text) => { 
                        const el = Array.from(document.querySelectorAll("li.objectTypeli")).find(e => e.innerText.includes(text)); 
                        if(el) el.click(); 
                    }"""
                    await page.evaluate(js_click_script, mt)
                    await asyncio.sleep(2) # 等待DOM刷新
                    
                    fields = await page.evaluate(script)
                    
                    # 只打印特有字段 (排除基础的联系人电话价格机型年限标题等)
                    base_fields = ['*联系人', '*联系电话', '*转让价格', '一句话广告', '标题', '*机型', '*出厂年限']
                    for field in fields:
                        if field['label'] not in base_fields:
                            print(f"{mt} -> {field}")
                            
                except Exception as e:
                    print(f"Error testing {mt}: {e}")
                
        finally:
            await context.close()
if __name__ == "__main__":
    asyncio.run(main())
