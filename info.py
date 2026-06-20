import os
import sys
import platform
import requests
import json
from datetime import datetime

def get_disk_info():
    """Lấy thông tin tất cả ổ đĩa trên hệ thống"""
    system = platform.system()
    disk_info = []
    
    if system == "Windows":
        # Windows: Dùng os.listdrives() hoặc psutil
        try:
            import psutil
            partitions = psutil.disk_partitions()
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info.append({
                        "drive": partition.device,
                        "mount": partition.mountpoint,
                        "total_gb": round(usage.total / (1024**3), 2),
                        "used_gb": round(usage.used / (1024**3), 2),
                        "free_gb": round(usage.free / (1024**3), 2),
                        "percent": usage.percent
                    })
                except:
                    pass
        except ImportError:
            # Fallback nếu không có psutil
            import string
            from ctypes import windll
            drives = []
            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drive = f"{letter}:\\"
                    try:
                        free_bytes = windll.kernel32.GetDiskFreeSpaceExW(drive, None, None, None)
                        if free_bytes:
                            total, free = free_bytes[0], free_bytes[2]
                            used = total - free
                            disk_info.append({
                                "drive": drive,
                                "mount": drive,
                                "total_gb": round(total / (1024**3), 2),
                                "used_gb": round(used / (1024**3), 2),
                                "free_gb": round(free / (1024**3), 2),
                                "percent": round((used / total) * 100, 1) if total > 0 else 0
                            })
                    except:
                        pass
                bitmask >>= 1
    
    elif system == "Linux" or system == "Darwin":
        # Linux/Mac: Dùng lệnh df hoặc psutil
        try:
            import psutil
            partitions = psutil.disk_partitions()
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info.append({
                        "drive": partition.device,
                        "mount": partition.mountpoint,
                        "total_gb": round(usage.total / (1024**3), 2),
                        "used_gb": round(usage.used / (1024**3), 2),
                        "free_gb": round(usage.free / (1024**3), 2),
                        "percent": usage.percent
                    })
                except:
                    pass
        except ImportError:
            # Fallback dùng lệnh df
            import subprocess
            try:
                result = subprocess.run(['df', '-h'], capture_output=True, text=True)
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:  # Bỏ header
                    parts = line.split()
                    if len(parts) >= 6:
                        disk_info.append({
                            "drive": parts[0],
                            "mount": parts[-1],
                            "total": parts[1],
                            "used": parts[2],
                            "free": parts[3],
                            "percent": parts[4]
                        })
            except:
                pass
    
    return disk_info, system

def get_system_info():
    """Lấy thông tin hệ thống cơ bản"""
    info = {
        "hostname": platform.node(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "python_version": sys.version,
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Lấy RAM info nếu có psutil
    try:
        import psutil
        mem = psutil.virtual_memory()
        info["ram_total_gb"] = round(mem.total / (1024**3), 2)
        info["ram_used_gb"] = round(mem.used / (1024**3), 2)
        info["ram_percent"] = mem.percent
    except:
        pass
    
    return info

def send_to_discord_webhook(webhook_url, system_info, disk_info):
    """Gửi thông tin qua Discord Webhook"""
    
    # Tạo embed cho Discord
    embeds = []
    
    # Embed 1: Thông tin hệ thống
    sys_embed = {
        "title": "🖥️ THÔNG TIN HỆ THỐNG",
        "color": 0x00ff00,
        "fields": [
            {"name": "Hostname", "value": system_info.get("hostname", "N/A"), "inline": True},
            {"name": "Hệ điều hành", "value": f"{system_info.get('system', 'N/A')} {system_info.get('release', 'N/A')}", "inline": True},
            {"name": "Kiến trúc", "value": system_info.get("architecture", "N/A"), "inline": True},
            {"name": "CPU", "value": system_info.get("processor", "N/A")[:100], "inline": False},
            {"name": "Thời gian", "value": system_info.get("current_time", "N/A"), "inline": False}
        ],
        "footer": {"text": "Disk Monitor Bot"}
    }
    
    # Thêm RAM info nếu có
    if "ram_total_gb" in system_info:
        sys_embed["fields"].extend([
            {"name": "RAM Tổng", "value": f"{system_info['ram_total_gb']} GB", "inline": True},
            {"name": "RAM Đã dùng", "value": f"{system_info['ram_used_gb']} GB ({system_info['ram_percent']}%)", "inline": True}
        ])
    
    embeds.append(sys_embed)
    
    # Embed 2: Thông tin ổ đĩa
    disk_embed = {
        "title": "💾 THÔNG TIN Ổ ĐĨA",
        "color": 0x0099ff,
        "fields": [],
        "footer": {"text": f"Tổng số ổ đĩa: {len(disk_info)}"}
    }
    
    for disk in disk_info:
        # Xác định icon dựa vào % sử dụng
        if disk.get("percent", 0) > 90:
            icon = "🔴"
        elif disk.get("percent", 0) > 70:
            icon = "🟡"
        else:
            icon = "🟢"
        
        field_value = (
            f"**Tổng:** {disk.get('total_gb', disk.get('total', 'N/A'))} GB\n"
            f"**Đã dùng:** {disk.get('used_gb', disk.get('used', 'N/A'))} GB\n"
            f"**Còn trống:** {disk.get('free_gb', disk.get('free', 'N/A'))} GB\n"
            f"**Sử dụng:** {disk.get('percent', 'N/A')}%"
        )
        
        disk_embed["fields"].append({
            "name": f"{icon} {disk.get('drive', 'Unknown')} - {disk.get('mount', '')}",
            "value": field_value,
            "inline": True
        })
    
    embeds.append(disk_embed)
    
    # Tạo payload
    payload = {
        "content": "📊 **BÁO CÁO DUNG LƯỢNG Ổ ĐĨA**",
        "embeds": embeds
    }
    
    # Gửi webhook
    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(webhook_url, data=json.dumps(payload), headers=headers)
        
        if response.status_code == 204:
            print("✅ Đã gửi thông tin thành công qua Discord Webhook!")
            return True
        else:
            print(f"❌ Lỗi gửi webhook: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Lỗi kết nối: {e}")
        return False

def send_plain_text_to_discord(webhook_url, system_info, disk_info):
    """Gửi thông tin dạng text đơn giản (nếu embed không hoạt động)"""
    
    message = "📊 **BÁO CÁO DUNG LƯỢNG Ổ ĐĨA**\n"
    message += "```\n"
    message += f"Hostname: {system_info.get('hostname', 'N/A')}\n"
    message += f"System: {system_info.get('system', 'N/A')} {system_info.get('release', 'N/A')}\n"
    message += f"Time: {system_info.get('current_time', 'N/A')}\n"
    
    if "ram_total_gb" in system_info:
        message += f"RAM: {system_info['ram_used_gb']}GB / {system_info['ram_total_gb']}GB ({system_info['ram_percent']}%)\n"
    
    message += "\n--- DISK INFO ---\n"
    for disk in disk_info:
        message += f"{disk.get('drive', 'N/A')} [{disk.get('mount', '')}]\n"
        message += f"  Total: {disk.get('total_gb', disk.get('total', 'N/A'))} GB\n"
        message += f"  Used:  {disk.get('used_gb', disk.get('used', 'N/A'))} GB\n"
        message += f"  Free:  {disk.get('free_gb', disk.get('free', 'N/A'))} GB\n"
        message += f"  Usage: {disk.get('percent', 'N/A')}%\n\n"
    
    message += "```"
    
    try:
        payload = {"content": message}
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 204:
            print("✅ Đã gửi text thành công!")
            return True
        else:
            print(f"❌ Lỗi: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Lỗi: {e}")
        return False

def main():
    # Webhook URL của bạn
    WEBHOOK_URL = ""
    
    print("=" * 50)
    print("DISK MONITOR - LIỆT KÊ DUNG LƯỢNG Ổ ĐĨA")
    print("=" * 50)
    
    # Lấy thông tin hệ thống
    print("\n[1] Đang thu thập thông tin hệ thống...")
    system_info = get_system_info()
    print(f"  ✓ Hostname: {system_info['hostname']}")
    print(f"  ✓ OS: {system_info['system']} {system_info['release']}")
    
    # Lấy thông tin ổ đĩa
    print("\n[2] Đang quét ổ đĩa...")
    disk_info, system = get_disk_info()
    
    if not disk_info:
        print("  ❌ Không tìm thấy ổ đĩa nào!")
        return
    
    print(f"  ✓ Tìm thấy {len(disk_info)} ổ đĩa:")
    for disk in disk_info:
        drive = disk.get('drive', 'Unknown')
        used = disk.get('used_gb', disk.get('used', 'N/A'))
        total = disk.get('total_gb', disk.get('total', 'N/A'))
        percent = disk.get('percent', 'N/A')
        print(f"    • {drive}: {used}GB / {total}GB ({percent}%)")
    
    # Gửi qua webhook
    print(f"\n[3] Đang gửi dữ liệu qua Discord Webhook...")
    
    # Thử gửi dạng embed trước
    success = send_to_discord_webhook(WEBHOOK_URL, system_info, disk_info)
    
    # Nếu thất bại, gửi dạng text
    if not success:
        print("\n[4] Thử lại với định dạng text...")
        send_plain_text_to_discord(WEBHOOK_URL, system_info, disk_info)
    
    print("\n" + "=" * 50)
    print("HOÀN THÀNH!")
    print("=" * 50)

if __name__ == "__main__":
    main()
