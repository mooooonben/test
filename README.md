# 🔍 多链钱包余额监控工具

一个支持 **Ethereum (ETH)**、**Solana (SOL)** 和 **Aptos (APT)** 的钱包余额实时监控工具。

## ✨ 功能特性

- 🔗 支持多链监控：ETH、SOL、APT
- 💰 实时获取钱包余额和代币余额
- 🏦 **DeFi 仓位检测**：Lido、Aave、Compound、Curve、EtherFi 等
- 💵 自动获取 USD 价格（通过 CoinGecko）
- 📊 余额变化检测和提醒
- 🔔 支持 Telegram 和 Discord 通知
- ⚡ 异步并发查询，高效快速

## 📦 安装

### 方式一：一键设置（推荐）

```bash
git clone https://github.com/mooooonben/test.git
cd test
chmod +x setup.sh
./setup.sh
```

### 方式二：手动设置虚拟环境

```bash
# 克隆项目
git clone https://github.com/mooooonben/test.git
cd test

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 创建本地配置（不会被提交到 Git）
cp config.yaml config.local.yaml
```

## ⚙️ 配置

编辑 `config.yaml` 文件，添加你要监控的钱包地址：

```yaml
# 监控间隔（秒）
monitor_interval: 60

# 余额变化提醒阈值（百分比）
alert_threshold_percent: 5

# Ethereum 配置
ethereum:
  rpc_url: "https://eth.llamarpc.com"
  wallets:
    - address: "0x你的钱包地址"
      name: "我的ETH钱包"

# Solana 配置
solana:
  rpc_url: "https://api.mainnet-beta.solana.com"
  wallets:
    - address: "你的SOL钱包地址"
      name: "我的SOL钱包"

# Aptos 配置
aptos:
  api_url: "https://fullnode.mainnet.aptoslabs.com/v1"
  wallets:
    - address: "0x你的APT钱包地址"
      name: "我的APT钱包"
```

### 配置通知（可选）

#### Telegram 通知

```yaml
notifications:
  telegram:
    enabled: true
    bot_token: "YOUR_BOT_TOKEN"
    chat_id: "YOUR_CHAT_ID"
```

#### Discord 通知

```yaml
notifications:
  discord:
    enabled: true
    webhook_url: "YOUR_DISCORD_WEBHOOK_URL"
```

## 🚀 使用方法

### 持续监控模式

```bash
python wallet_monitor.py
```

### 单次检查模式

```bash
python wallet_monitor.py --once
```

### 指定配置文件

```bash
python wallet_monitor.py -c /path/to/your/config.yaml
```

## 📝 输出示例

```
🚀 钱包余额监控启动
📊 监控链: ethereum, solana, aptos
⏱️  检查间隔: 60 秒

============================================================
⏰ 检查时间: 2024-01-15 14:30:00
============================================================
  [Ethereum] ETH钱包1: 1.234567 ETH ($2,469.13)
  [Solana] SOL钱包1: 100.000000 SOL ($9,800.00)
  [Aptos] APT钱包1: 500.000000 APT ($4,500.00)
```

## 🔧 高级用法

### 自定义 RPC 节点

建议使用专用的 RPC 节点以获得更好的性能和可靠性：

- **Ethereum**: [Infura](https://infura.io/), [Alchemy](https://www.alchemy.com/), [QuickNode](https://www.quicknode.com/)
- **Solana**: [QuickNode](https://www.quicknode.com/), [Helius](https://helius.dev/)
- **Aptos**: [Aptos Labs](https://aptoslabs.com/)

### 作为后台服务运行

使用 `nohup` 或 `screen`：

```bash
nohup python wallet_monitor.py > monitor.log 2>&1 &
```

或使用 `systemd` 服务（Linux）：

```ini
[Unit]
Description=Wallet Balance Monitor
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/wallet-monitor
ExecStart=/usr/bin/python3 wallet_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 📋 依赖

- Python 3.8+
- aiohttp
- pyyaml

## ⚠️ 注意事项

1. **RPC 限制**: 公共 RPC 节点可能有请求频率限制，建议使用自己的 API Key
2. **价格 API**: CoinGecko 免费 API 有请求限制，如需高频查询请使用付费 API
3. **安全性**: 不要在配置文件中存储私钥，本工具只需要公开的钱包地址

## 📄 许可证

MIT License
