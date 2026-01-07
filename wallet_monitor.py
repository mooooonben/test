#!/usr/bin/env python3
"""
多链钱包余额监控工具
支持 Ethereum (ETH), Solana (SOL), Aptos (APT)
"""

import asyncio
import aiohttp
import yaml
import json
import time
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod
from pathlib import Path


@dataclass
class WalletBalance:
    """钱包余额数据类"""
    chain: str
    address: str
    name: str
    balance: float
    symbol: str
    timestamp: datetime
    usd_value: Optional[float] = None


class ChainMonitor(ABC):
    """链监控基类"""
    
    def __init__(self, config: dict):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
    
    @abstractmethod
    async def get_balance(self, address: str) -> float:
        """获取钱包余额"""
        pass
    
    @property
    @abstractmethod
    def chain_name(self) -> str:
        """链名称"""
        pass
    
    @property
    @abstractmethod
    def symbol(self) -> str:
        """代币符号"""
        pass


class EthereumMonitor(ChainMonitor):
    """Ethereum 链监控"""
    
    @property
    def chain_name(self) -> str:
        return "Ethereum"
    
    @property
    def symbol(self) -> str:
        return "ETH"
    
    async def get_balance(self, address: str) -> float:
        """获取 ETH 余额"""
        rpc_url = self.config.get("rpc_url", "https://eth.llamarpc.com")
        
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [address, "latest"],
            "id": 1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(rpc_url, json=payload) as response:
                data = await response.json()
                if "result" in data:
                    # 将 Wei 转换为 ETH
                    balance_wei = int(data["result"], 16)
                    return balance_wei / 1e18
                else:
                    raise Exception(f"ETH RPC Error: {data.get('error', 'Unknown error')}")


class SolanaMonitor(ChainMonitor):
    """Solana 链监控"""
    
    @property
    def chain_name(self) -> str:
        return "Solana"
    
    @property
    def symbol(self) -> str:
        return "SOL"
    
    async def get_balance(self, address: str) -> float:
        """获取 SOL 余额"""
        rpc_url = self.config.get("rpc_url", "https://api.mainnet-beta.solana.com")
        
        payload = {
            "jsonrpc": "2.0",
            "method": "getBalance",
            "params": [address],
            "id": 1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(rpc_url, json=payload) as response:
                data = await response.json()
                if "result" in data:
                    # 将 Lamports 转换为 SOL
                    balance_lamports = data["result"]["value"]
                    return balance_lamports / 1e9
                else:
                    raise Exception(f"SOL RPC Error: {data.get('error', 'Unknown error')}")


class AptosMonitor(ChainMonitor):
    """Aptos 链监控"""
    
    @property
    def chain_name(self) -> str:
        return "Aptos"
    
    @property
    def symbol(self) -> str:
        return "APT"
    
    async def get_balance(self, address: str) -> float:
        """获取 APT 余额"""
        api_url = self.config.get("api_url", "https://fullnode.mainnet.aptoslabs.com/v1")
        
        # Aptos 账户资源 API
        url = f"{api_url}/accounts/{address}/resource/0x1::coin::CoinStore<0x1::aptos_coin::AptosCoin>"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # 将 Octas 转换为 APT
                    balance_octas = int(data["data"]["coin"]["value"])
                    return balance_octas / 1e8
                elif response.status == 404:
                    # 账户不存在或没有 APT
                    return 0.0
                else:
                    text = await response.text()
                    raise Exception(f"APT API Error: {response.status} - {text}")


class PriceService:
    """价格服务 - 获取代币 USD 价格"""
    
    COINGECKO_IDS = {
        "ETH": "ethereum",
        "SOL": "solana",
        "APT": "aptos"
    }
    
    def __init__(self):
        self.prices: Dict[str, float] = {}
        self.last_update: Optional[datetime] = None
    
    async def update_prices(self) -> Dict[str, float]:
        """从 CoinGecko 更新价格"""
        ids = ",".join(self.COINGECKO_IDS.values())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        for symbol, coin_id in self.COINGECKO_IDS.items():
                            if coin_id in data:
                                self.prices[symbol] = data[coin_id]["usd"]
                        self.last_update = datetime.now()
        except Exception as e:
            print(f"⚠️  获取价格失败: {e}")
        
        return self.prices
    
    def get_price(self, symbol: str) -> Optional[float]:
        """获取代币 USD 价格"""
        return self.prices.get(symbol)


class NotificationService:
    """通知服务"""
    
    def __init__(self, config: dict):
        self.config = config
    
    async def send_telegram(self, message: str):
        """发送 Telegram 通知"""
        tg_config = self.config.get("telegram", {})
        if not tg_config.get("enabled"):
            return
        
        bot_token = tg_config.get("bot_token")
        chat_id = tg_config.get("chat_id")
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(url, json=payload)
        except Exception as e:
            print(f"⚠️  Telegram 通知发送失败: {e}")
    
    async def send_discord(self, message: str):
        """发送 Discord 通知"""
        discord_config = self.config.get("discord", {})
        if not discord_config.get("enabled"):
            return
        
        webhook_url = discord_config.get("webhook_url")
        payload = {"content": message}
        
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(webhook_url, json=payload)
        except Exception as e:
            print(f"⚠️  Discord 通知发送失败: {e}")
    
    async def notify(self, message: str):
        """发送所有启用的通知"""
        await asyncio.gather(
            self.send_telegram(message),
            self.send_discord(message),
            return_exceptions=True
        )


class WalletMonitor:
    """钱包监控主类"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.monitors: Dict[str, ChainMonitor] = {}
        self.price_service = PriceService()
        self.notification_service = NotificationService(
            self.config.get("notifications", {})
        )
        self.previous_balances: Dict[str, float] = {}
        
        self._init_monitors()
    
    def _load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def _init_monitors(self):
        """初始化各链监控器"""
        if "ethereum" in self.config:
            self.monitors["ethereum"] = EthereumMonitor(self.config["ethereum"])
        
        if "solana" in self.config:
            self.monitors["solana"] = SolanaMonitor(self.config["solana"])
        
        if "aptos" in self.config:
            self.monitors["aptos"] = AptosMonitor(self.config["aptos"])
    
    async def check_balance(self, chain: str, wallet: dict) -> Optional[WalletBalance]:
        """检查单个钱包余额"""
        monitor = self.monitors.get(chain)
        if not monitor:
            return None
        
        try:
            balance = await monitor.get_balance(wallet["address"])
            price = self.price_service.get_price(monitor.symbol)
            usd_value = balance * price if price else None
            
            return WalletBalance(
                chain=monitor.chain_name,
                address=wallet["address"],
                name=wallet.get("name", wallet["address"][:10] + "..."),
                balance=balance,
                symbol=monitor.symbol,
                timestamp=datetime.now(),
                usd_value=usd_value
            )
        except Exception as e:
            print(f"❌ 获取 {chain} 钱包 {wallet.get('name', wallet['address'])} 余额失败: {e}")
            return None
    
    async def check_all_balances(self) -> List[WalletBalance]:
        """检查所有钱包余额"""
        results = []
        tasks = []
        
        for chain, monitor in self.monitors.items():
            chain_config = self.config.get(chain, {})
            wallets = chain_config.get("wallets", [])
            
            for wallet in wallets:
                tasks.append(self.check_balance(chain, wallet))
        
        balances = await asyncio.gather(*tasks)
        results = [b for b in balances if b is not None]
        
        return results
    
    def _check_balance_change(self, balance: WalletBalance) -> Optional[float]:
        """检查余额变化"""
        key = f"{balance.chain}:{balance.address}"
        previous = self.previous_balances.get(key)
        
        if previous is not None and previous > 0:
            change_percent = ((balance.balance - previous) / previous) * 100
            threshold = self.config.get("alert_threshold_percent", 5)
            
            if abs(change_percent) >= threshold:
                return change_percent
        
        self.previous_balances[key] = balance.balance
        return None
    
    def _format_balance(self, balance: WalletBalance) -> str:
        """格式化余额输出"""
        usd_str = f" (${balance.usd_value:,.2f})" if balance.usd_value else ""
        return f"  [{balance.chain}] {balance.name}: {balance.balance:,.6f} {balance.symbol}{usd_str}"
    
    async def run_once(self) -> List[WalletBalance]:
        """运行一次检查"""
        print(f"\n{'='*60}")
        print(f"⏰ 检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        
        # 更新价格
        await self.price_service.update_prices()
        
        # 检查余额
        balances = await self.check_all_balances()
        
        # 输出结果
        for balance in balances:
            print(self._format_balance(balance))
            
            # 检查余额变化
            change = self._check_balance_change(balance)
            if change is not None:
                direction = "📈 增加" if change > 0 else "📉 减少"
                alert_msg = f"⚠️ {balance.name} 余额{direction} {abs(change):.2f}%"
                print(f"    {alert_msg}")
                await self.notification_service.notify(
                    f"🔔 钱包余额变化提醒\n"
                    f"链: {balance.chain}\n"
                    f"钱包: {balance.name}\n"
                    f"地址: {balance.address}\n"
                    f"变化: {direction} {abs(change):.2f}%\n"
                    f"当前余额: {balance.balance:,.6f} {balance.symbol}"
                )
        
        return balances
    
    async def run(self):
        """持续运行监控"""
        interval = self.config.get("monitor_interval", 60)
        
        print("🚀 钱包余额监控启动")
        print(f"📊 监控链: {', '.join(self.monitors.keys())}")
        print(f"⏱️  检查间隔: {interval} 秒")
        
        while True:
            try:
                await self.run_once()
            except Exception as e:
                print(f"❌ 监控出错: {e}")
            
            await asyncio.sleep(interval)


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="多链钱包余额监控工具")
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="只运行一次检查"
    )
    
    args = parser.parse_args()
    
    try:
        monitor = WalletMonitor(args.config)
        
        if args.once:
            await monitor.run_once()
        else:
            await monitor.run()
    
    except FileNotFoundError as e:
        print(f"❌ 错误: {e}")
        print("请先创建配置文件，参考 config.yaml.example")
    except KeyboardInterrupt:
        print("\n👋 监控已停止")


if __name__ == "__main__":
    asyncio.run(main())
