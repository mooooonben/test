#!/usr/bin/env python3
"""
多链钱包余额监控工具
支持 Ethereum (ETH), Solana (SOL), Aptos (APT)
包括原生代币和其他代币余额
"""

import asyncio
import aiohttp
import yaml
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from pathlib import Path


@dataclass
class TokenBalance:
    """代币余额数据类"""
    symbol: str
    name: str
    balance: float
    contract_address: Optional[str] = None
    decimals: int = 18
    usd_value: Optional[float] = None
    logo_url: Optional[str] = None


@dataclass
class WalletBalance:
    """钱包余额数据类"""
    chain: str
    address: str
    name: str
    native_balance: float
    native_symbol: str
    timestamp: datetime
    native_usd_value: Optional[float] = None
    tokens: List[TokenBalance] = field(default_factory=list)


class ChainMonitor(ABC):
    """链监控基类"""
    
    def __init__(self, config: dict):
        self.config = config
    
    @abstractmethod
    async def get_balance(self, address: str) -> Tuple[float, List[TokenBalance]]:
        """获取钱包余额，返回 (原生代币余额, 其他代币列表)"""
        pass
    
    @property
    @abstractmethod
    def chain_name(self) -> str:
        """链名称"""
        pass
    
    @property
    @abstractmethod
    def symbol(self) -> str:
        """原生代币符号"""
        pass


class EthereumMonitor(ChainMonitor):
    """Ethereum 链监控 - 支持 ERC-20 代币"""
    
    # 常见 ERC-20 代币合约地址和信息
    KNOWN_TOKENS = {
        "0xdAC17F958D2ee523a2206206994597C13D831ec7": ("USDT", "Tether USD", 6),
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": ("USDC", "USD Coin", 6),
        "0x6B175474E89094C44Da98b954EescdeCB5": ("DAI", "Dai Stablecoin", 18),
        "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599": ("WBTC", "Wrapped BTC", 8),
        "0x514910771AF9Ca656af840dff83E8264EcF986CA": ("LINK", "Chainlink", 18),
        "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984": ("UNI", "Uniswap", 18),
        "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0": ("MATIC", "Polygon", 18),
        "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE": ("SHIB", "Shiba Inu", 18),
        "0x6982508145454Ce325dDbE47a25d4ec3d2311933": ("PEPE", "Pepe", 18),
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": ("WETH", "Wrapped Ether", 18),
        "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9": ("AAVE", "Aave", 18),
        "0x4d224452801ACEd8B2F0aebE155379bb5D594381": ("APE", "ApeCoin", 18),
    }
    
    @property
    def chain_name(self) -> str:
        return "Ethereum"
    
    @property
    def symbol(self) -> str:
        return "ETH"
    
    async def get_native_balance(self, session: aiohttp.ClientSession, address: str) -> float:
        """获取 ETH 余额"""
        rpc_url = self.config.get("rpc_url", "https://eth.llamarpc.com")
        
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [address, "latest"],
            "id": 1
        }
        
        async with session.post(rpc_url, json=payload) as response:
            data = await response.json()
            if "result" in data:
                balance_wei = int(data["result"], 16)
                return balance_wei / 1e18
            return 0.0
    
    async def get_token_balance(self, session: aiohttp.ClientSession, 
                                 address: str, token_address: str, 
                                 decimals: int) -> float:
        """获取单个 ERC-20 代币余额"""
        rpc_url = self.config.get("rpc_url", "https://eth.llamarpc.com")
        
        # ERC-20 balanceOf 函数签名
        data = f"0x70a08231000000000000000000000000{address[2:].lower()}"
        
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": token_address, "data": data}, "latest"],
            "id": 1
        }
        
        try:
            async with session.post(rpc_url, json=payload) as response:
                result = await response.json()
                if "result" in result and result["result"] != "0x":
                    balance = int(result["result"], 16)
                    return balance / (10 ** decimals)
        except Exception:
            pass
        return 0.0
    
    async def get_balance(self, address: str) -> Tuple[float, List[TokenBalance]]:
        """获取 ETH 和所有 ERC-20 代币余额"""
        tokens = []
        
        async with aiohttp.ClientSession() as session:
            # 获取 ETH 余额
            native_balance = await self.get_native_balance(session, address)
            
            # 获取常见 ERC-20 代币余额
            for token_addr, (symbol, name, decimals) in self.KNOWN_TOKENS.items():
                try:
                    balance = await self.get_token_balance(session, address, token_addr, decimals)
                    if balance > 0:
                        tokens.append(TokenBalance(
                            symbol=symbol,
                            name=name,
                            balance=balance,
                            contract_address=token_addr,
                            decimals=decimals
                        ))
                except Exception:
                    continue
        
        return native_balance, tokens


class SolanaMonitor(ChainMonitor):
    """Solana 链监控 - 支持 SPL 代币"""
    
    # 缓存 Jupiter 代币列表
    _token_list_cache: Optional[Dict[str, dict]] = None
    _cache_time: Optional[datetime] = None
    
    @property
    def chain_name(self) -> str:
        return "Solana"
    
    @property
    def symbol(self) -> str:
        return "SOL"
    
    async def _load_token_list(self, session: aiohttp.ClientSession) -> Dict[str, dict]:
        """加载并缓存 Jupiter 代币列表"""
        # 检查缓存是否有效（1小时）
        if (self._token_list_cache is not None and 
            self._cache_time is not None and
            (datetime.now() - self._cache_time).seconds < 3600):
            return self._token_list_cache
        
        try:
            url = "https://token.jup.ag/all"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    tokens = await response.json()
                    SolanaMonitor._token_list_cache = {
                        t["address"]: t for t in tokens
                    }
                    SolanaMonitor._cache_time = datetime.now()
                    return SolanaMonitor._token_list_cache
        except Exception as e:
            print(f"⚠️  加载 Solana 代币列表失败: {e}")
        
        return {}
    
    async def get_balance(self, address: str) -> Tuple[float, List[TokenBalance]]:
        """获取 SOL 和所有 SPL 代币余额"""
        rpc_url = self.config.get("rpc_url", "https://api.mainnet-beta.solana.com")
        tokens = []
        native_balance = 0.0
        
        async with aiohttp.ClientSession() as session:
            # 加载代币列表
            token_list = await self._load_token_list(session)
            
            # 获取 SOL 余额
            payload = {
                "jsonrpc": "2.0",
                "method": "getBalance",
                "params": [address],
                "id": 1
            }
            
            async with session.post(rpc_url, json=payload) as response:
                data = await response.json()
                if "result" in data:
                    native_balance = data["result"]["value"] / 1e9
            
            # 获取所有 SPL 代币账户
            payload = {
                "jsonrpc": "2.0",
                "method": "getTokenAccountsByOwner",
                "params": [
                    address,
                    {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                    {"encoding": "jsonParsed"}
                ],
                "id": 2
            }
            
            async with session.post(rpc_url, json=payload) as response:
                data = await response.json()
                if "result" in data:
                    for account in data["result"].get("value", []):
                        try:
                            parsed = account["account"]["data"]["parsed"]["info"]
                            token_amount = parsed["tokenAmount"]
                            balance = float(token_amount["uiAmount"] or 0)
                            
                            if balance > 0:
                                mint = parsed["mint"]
                                
                                # 从缓存获取代币信息
                                token_info = token_list.get(mint, {})
                                symbol = token_info.get("symbol", mint[:8])
                                name = token_info.get("name", "Unknown Token")
                                
                                tokens.append(TokenBalance(
                                    symbol=symbol,
                                    name=name,
                                    balance=balance,
                                    contract_address=mint,
                                    decimals=int(token_amount["decimals"])
                                ))
                        except Exception:
                            continue
        
        return native_balance, tokens


class AptosMonitor(ChainMonitor):
    """Aptos 链监控 - 支持所有代币"""
    
    @property
    def chain_name(self) -> str:
        return "Aptos"
    
    @property
    def symbol(self) -> str:
        return "APT"
    
    async def get_balance(self, address: str) -> Tuple[float, List[TokenBalance]]:
        """获取 APT 和所有代币余额"""
        api_url = self.config.get("api_url", "https://fullnode.mainnet.aptoslabs.com/v1")
        tokens = []
        native_balance = 0.0
        
        async with aiohttp.ClientSession() as session:
            # 获取所有账户资源
            url = f"{api_url}/accounts/{address}/resources"
            
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        resources = await response.json()
                        
                        for resource in resources:
                            res_type = resource.get("type", "")
                            
                            # 匹配 CoinStore 资源
                            if "0x1::coin::CoinStore<" in res_type:
                                try:
                                    coin_type = res_type.split("<")[1].rstrip(">")
                                    value = int(resource["data"]["coin"]["value"])
                                    
                                    # 判断是否是原生 APT
                                    if coin_type == "0x1::aptos_coin::AptosCoin":
                                        native_balance = value / 1e8
                                    else:
                                        # 其他代币
                                        if value > 0:
                                            symbol = self._parse_coin_symbol(coin_type)
                                            tokens.append(TokenBalance(
                                                symbol=symbol,
                                                name=coin_type.split("::")[-1],
                                                balance=value / 1e8,
                                                contract_address=coin_type,
                                                decimals=8
                                            ))
                                except Exception:
                                    continue
            except Exception as e:
                print(f"APT API Error: {e}")
        
        return native_balance, tokens
    
    def _parse_coin_symbol(self, coin_type: str) -> str:
        """解析代币符号"""
        try:
            parts = coin_type.split("::")
            if len(parts) >= 3:
                return parts[-1][:10]
        except Exception:
            pass
        return coin_type[:10] + "..."


class PriceService:
    """价格服务 - 获取代币 USD 价格"""
    
    COINGECKO_IDS = {
        "ETH": "ethereum",
        "SOL": "solana",
        "APT": "aptos",
        "USDT": "tether",
        "USDC": "usd-coin",
        "DAI": "dai",
        "WBTC": "wrapped-bitcoin",
        "LINK": "chainlink",
        "UNI": "uniswap",
        "MATIC": "matic-network",
        "SHIB": "shiba-inu",
        "PEPE": "pepe",
        "WETH": "weth",
        "AAVE": "aave",
        "JUP": "jupiter-exchange-solana",
        "RAY": "raydium",
        "BONK": "bonk",
        "WIF": "dogwifcoin",
        "JTO": "jito-governance-token",
        "PYTH": "pyth-network",
        "RNDR": "render-token",
        "HNT": "helium",
        "SAMO": "samoyedcoin",
    }
    
    def __init__(self):
        self.prices: Dict[str, float] = {}
        self.last_update: Optional[datetime] = None
    
    async def update_prices(self) -> Dict[str, float]:
        """从 CoinGecko 更新价格"""
        ids = ",".join(set(self.COINGECKO_IDS.values()))
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        data = await response.json()
                        for symbol, coin_id in self.COINGECKO_IDS.items():
                            if coin_id in data and "usd" in data[coin_id]:
                                self.prices[symbol] = data[coin_id]["usd"]
                        self.last_update = datetime.now()
                    else:
                        print(f"⚠️  CoinGecko API 返回状态码: {response.status}")
        except Exception as e:
            print(f"⚠️  获取价格失败: {e}")
        
        return self.prices
    
    def get_price(self, symbol: str) -> Optional[float]:
        """获取代币 USD 价格"""
        # 稳定币默认 $1
        if symbol.upper() in ["USDT", "USDC", "DAI", "BUSD", "TUSD"]:
            return 1.0
        return self.prices.get(symbol.upper())


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
            native_balance, tokens = await monitor.get_balance(wallet["address"])
            price = self.price_service.get_price(monitor.symbol)
            native_usd = native_balance * price if price else None
            
            # 计算代币 USD 价值
            for token in tokens:
                token_price = self.price_service.get_price(token.symbol)
                if token_price:
                    token.usd_value = token.balance * token_price
            
            return WalletBalance(
                chain=monitor.chain_name,
                address=wallet["address"],
                name=wallet.get("name", wallet["address"][:10] + "..."),
                native_balance=native_balance,
                native_symbol=monitor.symbol,
                timestamp=datetime.now(),
                native_usd_value=native_usd,
                tokens=tokens
            )
        except Exception as e:
            print(f"❌ 获取 {chain} 钱包 {wallet.get('name', wallet['address'])} 余额失败: {e}")
            return None
    
    async def check_all_balances(self) -> List[WalletBalance]:
        """检查所有钱包余额"""
        tasks = []
        
        for chain, monitor in self.monitors.items():
            chain_config = self.config.get(chain, {})
            wallets = chain_config.get("wallets", [])
            
            for wallet in wallets:
                tasks.append(self.check_balance(chain, wallet))
        
        balances = await asyncio.gather(*tasks)
        return [b for b in balances if b is not None]
    
    def _format_balance(self, balance: WalletBalance) -> str:
        """格式化余额输出"""
        lines = []
        
        # 原生代币
        usd_str = f" (${balance.native_usd_value:,.2f})" if balance.native_usd_value else ""
        lines.append(f"\n  📍 [{balance.chain}] {balance.name}")
        lines.append(f"     ├─ {balance.native_balance:,.6f} {balance.native_symbol}{usd_str}")
        
        # 其他代币（按 USD 价值排序，有价值的在前）
        if balance.tokens:
            sorted_tokens = sorted(
                balance.tokens, 
                key=lambda t: (t.usd_value or 0, t.balance), 
                reverse=True
            )
            
            for i, token in enumerate(sorted_tokens):
                is_last = (i == len(sorted_tokens) - 1)
                prefix = "└─" if is_last else "├─"
                
                usd_str = f" (${token.usd_value:,.2f})" if token.usd_value else ""
                
                # 格式化余额显示
                if token.balance >= 1_000_000:
                    balance_str = f"{token.balance:,.0f}"
                elif token.balance >= 1:
                    balance_str = f"{token.balance:,.4f}"
                else:
                    balance_str = f"{token.balance:,.6f}"
                
                lines.append(f"     {prefix} {balance_str} {token.symbol}{usd_str}")
        
        return "\n".join(lines)
    
    async def run_once(self) -> List[WalletBalance]:
        """运行一次检查"""
        print(f"\n{'='*70}")
        print(f"⏰ 检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        
        # 更新价格
        print("📈 获取代币价格...")
        await self.price_service.update_prices()
        
        # 检查余额
        print("🔍 查询钱包余额...\n")
        balances = await self.check_all_balances()
        
        # 按链分组输出
        total_usd = 0.0
        
        for balance in balances:
            print(self._format_balance(balance))
            
            # 累计总价值
            if balance.native_usd_value:
                total_usd += balance.native_usd_value
            for token in balance.tokens:
                if token.usd_value:
                    total_usd += token.usd_value
        
        print(f"\n{'─'*70}")
        print(f"💰 总资产价值 (已知价格): ${total_usd:,.2f} USD")
        print(f"{'='*70}")
        
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
        print("请先创建配置文件，参考 config.yaml")
    except KeyboardInterrupt:
        print("\n👋 监控已停止")


if __name__ == "__main__":
    asyncio.run(main())
