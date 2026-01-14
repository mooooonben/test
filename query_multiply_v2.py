#!/usr/bin/env python3
"""
查询 Jupiter Multiply 仓位信息 - 更全面的查询
"""

import asyncio
import aiohttp
import json

TARGET_ADDRESS = "FbbkfhPhf58PbJ8WEzYZrUsuyNYRTvFe7HgUMWT9uUPW"

async def try_api(session: aiohttp.ClientSession, url: str, method: str = "GET", headers: dict = None) -> dict:
    """尝试调用 API"""
    try:
        if headers is None:
            headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        
        async with session.request(method, url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
            status = response.status
            if status == 200:
                try:
                    data = await response.json()
                    return {"status": status, "data": data, "success": True}
                except:
                    text = await response.text()
                    return {"status": status, "text": text[:500], "success": True}
            else:
                text = await response.text()
                return {"status": status, "error": text[:200], "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


async def main():
    print("=" * 80)
    print(f"🔍 查询 Jupiter Multiply 仓位: {TARGET_ADDRESS}")
    print("=" * 80)
    
    async with aiohttp.ClientSession() as session:
        
        # ========== Hubble Protocol / Kamino APIs ==========
        print("\n" + "=" * 40)
        print("📊 Hubble/Kamino API 查询")
        print("=" * 40)
        
        hubble_apis = [
            # Hubble Protocol (Kamino 母公司)
            f"https://api.hubbleprotocol.io/kamino/users/{TARGET_ADDRESS}",
            f"https://api.hubbleprotocol.io/v2/kamino/users/{TARGET_ADDRESS}",
            f"https://api.hubbleprotocol.io/v2/kamino/users/{TARGET_ADDRESS}/obligations",
            f"https://api.hubbleprotocol.io/kamino/obligations?owner={TARGET_ADDRESS}",
            
            # Kamino Finance 直接 API
            f"https://api.kamino.finance/users/{TARGET_ADDRESS}",
            f"https://api.kamino.finance/users/{TARGET_ADDRESS}/obligations",
            f"https://api.kamino.finance/obligations?wallet={TARGET_ADDRESS}",
            
            # Kamino Multiply 相关
            f"https://api.kamino.finance/multiply/positions/{TARGET_ADDRESS}",
            f"https://api.hubbleprotocol.io/multiply/{TARGET_ADDRESS}",
        ]
        
        for url in hubble_apis:
            result = await try_api(session, url)
            if result.get("success") and result.get("data"):
                print(f"\n✅ {url}")
                data = result.get("data")
                if isinstance(data, (dict, list)):
                    print(json.dumps(data, indent=2)[:2000])
                else:
                    print(f"   {data}")
            else:
                print(f"❌ {url}: {result.get('status', 'error')} - {result.get('error', '')[:50]}")
        
        # ========== Jupiter APIs ==========
        print("\n" + "=" * 40)
        print("📊 Jupiter API 查询")
        print("=" * 40)
        
        jupiter_apis = [
            # Jupiter Perps
            f"https://perps-api.jup.ag/v1/positions?wallet={TARGET_ADDRESS}",
            f"https://perps-api.jup.ag/positions?wallet={TARGET_ADDRESS}",
            
            # Jupiter 用户数据
            f"https://api.jup.ag/users/{TARGET_ADDRESS}",
            f"https://quote-api.jup.ag/v6/user/{TARGET_ADDRESS}",
            
            # Jupiter Multiply (如果有专门的端点)
            f"https://api.jup.ag/multiply/positions?wallet={TARGET_ADDRESS}",
            f"https://multiply.jup.ag/api/positions/{TARGET_ADDRESS}",
        ]
        
        for url in jupiter_apis:
            result = await try_api(session, url)
            if result.get("success") and result.get("data"):
                print(f"\n✅ {url}")
                data = result.get("data")
                if isinstance(data, (dict, list)):
                    print(json.dumps(data, indent=2)[:2000])
                else:
                    print(f"   {data}")
            else:
                print(f"❌ {url}: {result.get('status', 'error')} - {result.get('error', '')[:50]}")
        
        # ========== Solana RPC 查询代币详情 ==========
        print("\n" + "=" * 40)
        print("📊 Solana RPC 代币详情")
        print("=" * 40)
        
        rpc_url = "https://api.mainnet-beta.solana.com"
        
        # 获取所有代币账户
        payload = {
            "jsonrpc": "2.0",
            "method": "getTokenAccountsByOwner",
            "params": [
                TARGET_ADDRESS,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"}
            ],
            "id": 1
        }
        
        async with session.post(rpc_url, json=payload) as response:
            data = await response.json()
            if "result" in data:
                print(f"\n找到 {len(data['result']['value'])} 个代币账户:")
                for account in data["result"]["value"]:
                    try:
                        parsed = account["account"]["data"]["parsed"]["info"]
                        mint = parsed["mint"]
                        balance = float(parsed["tokenAmount"]["uiAmount"] or 0)
                        decimals = parsed["tokenAmount"]["decimals"]
                        
                        if balance > 0:
                            print(f"\n   Mint: {mint}")
                            print(f"   余额: {balance} (decimals: {decimals})")
                            print(f"   账户: {account['pubkey']}")
                    except Exception as e:
                        pass
        
        # ========== 尝试 Helius API (如果可用) ==========
        print("\n" + "=" * 40)
        print("📊 尝试其他 DeFi 聚合 API")
        print("=" * 40)
        
        other_apis = [
            # DeFiLlama
            f"https://yields.llama.fi/chart/{TARGET_ADDRESS}",
            
            # Step Finance (Solana 仪表盘)
            f"https://api.step.finance/v1/wallet/{TARGET_ADDRESS}",
            
            # Sonar Watch
            f"https://api.sonar.watch/v1/portfolio/{TARGET_ADDRESS}",
        ]
        
        for url in other_apis:
            result = await try_api(session, url)
            if result.get("success"):
                print(f"\n✅ {url}")
                data = result.get("data") or result.get("text")
                if isinstance(data, (dict, list)):
                    # 只打印相关部分
                    print(json.dumps(data, indent=2)[:1500])
                else:
                    print(f"   {str(data)[:500]}")
            else:
                print(f"❌ {url}: {result.get('status', 'error')}")


if __name__ == "__main__":
    asyncio.run(main())
