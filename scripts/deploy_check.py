#!/usr/bin/env python3
"""
部署前自动检查脚本
用法：python scripts/deploy_check.py
作用：部署前自动验证，避免重复踩坑
"""
import subprocess
import sys
import requests

def run_cmd(cmd):
    """运行命令并返回输出"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def check_container_network():
    """检查容器是否在正确网络"""
    print("\n🔍 检查容器网络...")
    ok, output = run_cmd("docker network ls --filter name=quantdinger --format '{{.Name}}'")
    if not ok:
        print("  ❌ 找不到quantdinger网络")
        return False
    
    ok, output = run_cmd("docker ps --filter name=quantdinger-backend --format '{{.Names}}'")
    if ok and "quantdinger-backend" in output:
        print("  ✅ 后端容器在运行")
    else:
        print("  ⚠️  后端容器未运行")
        return False
    
    print("  ✅ 容器网络检查通过")
    return True

def check_api_health():
    """检查API健康"""
    print("\n🔍 检查API健康...")
    try:
        resp = requests.get("http://localhost:5000/api/health", timeout=5)
        if resp.status_code == 200:
            print("  ✅ API健康检查通过 (200 OK)")
            return True
        else:
            print(f"  ❌ API返回 {resp.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ API连接失败: {e}")
        print("  💡 提示：检查后端容器是否在运行，docker network是否正确")
        return False

def check_frontend_proxy():
    """检查前端代理"""
    print("\n🔍 检查前端代理...")
    try:
        resp = requests.get("http://localhost:8888/api/health", timeout=5)
        if resp.status_code == 200:
            print("  ✅ 前端代理正常 (200 OK)")
            return True
        else:
            print(f"  ⚠️  前端代理返回 {resp.status_code}")
            print("  💡 提示：检查nginx upstream配置，容器DNS别名是否正确")
            return False
    except Exception as e:
        print(f"  ⚠️  前端连接失败: {e}")
        return False

def check_env_vars():
    """检查环境变量"""
    print("\n🔍 检查环境变量...")
    ok, output = run_cmd("docker exec quantdinger-backend env | grep DATABASE_URL")
    if ok and "postgresql" in output:
        print("  ✅ DATABASE_URL 已设置")
        print("  💡 提醒：后端用的是DATABASE_URL完整连接字符串，不是POSTGRES_PASSWORD")
        return True
    else:
        print("  ❌ DATABASE_URL 未设置")
        print("  💡 提示：后端环境变量名是DATABASE_URL，格式postgresql://user:pass@host:port/dbname")
        return False

def main():
    print("=" * 50)
    print("🚀 部署前自动检查 - 避免重复踩坑")
    print("=" * 50)
    
    checks = [
        check_container_network,
        check_api_health,
        check_frontend_proxy,
        check_env_vars,
    ]
    
    passed = 0
    failed = 0
    
    for check in checks:
        try:
            if check():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ❌ 检查出错: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"检查完成：✅ {passed} 通过 / ❌ {failed} 失败")
    
    if failed > 0:
        print("\n💡 常见踩坑提示：")
        print("  - 容器不在网络？→ docker network connect <网络名> <容器名>")
        print("  - API 502？→ 检查nginx upstream，容器DNS别名必须一致")
        print("  - 数据库连不上？→ 环境变量是DATABASE_URL，不是POSTGRES_PASSWORD")
        print("  - 改了前端看不到？→ 必须docker cp进容器，强制刷新浏览器")
        sys.exit(1)
    else:
        print("\n✅ 全部检查通过，可以部署！")
        sys.exit(0)

if __name__ == "__main__":
    main()
