#!/bin/bash
# 一键设置脚本

echo "🚀 设置钱包监控环境..."

# 检查 Python 版本
if ! command -v python3 &> /dev/null; then
    echo "❌ 请先安装 Python 3.8+"
    exit 1
fi

# 创建虚拟环境
echo "📦 创建虚拟环境..."
python3 -m venv venv

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "📥 安装依赖..."
pip install -r requirements.txt -q

# 创建本地配置
if [ ! -f config.local.yaml ]; then
    echo "📝 创建本地配置文件..."
    cp config.yaml config.local.yaml
    echo "⚠️  请编辑 config.local.yaml 填入你的钱包地址"
fi

echo ""
echo "✅ 设置完成！"
echo ""
echo "使用方法:"
echo "  1. 激活环境:  source venv/bin/activate"
echo "  2. 编辑配置:  nano config.local.yaml"
echo "  3. 运行监控:  python wallet_monitor.py -c config.local.yaml --once"
echo ""
