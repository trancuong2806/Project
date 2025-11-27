import tkinter as tk
import random
import threading
import time
import math

# Hàm tính toán các điểm tọa độ tạo nên hình trái tim
def generate_heart_points(num_points=100):
    points = []
    for i in range(num_points):
        # t chạy từ 0 đến 2*pi
        t = (i / num_points) * 2 * math.pi
        
        # Công thức hình trái tim
        x = 16 * (math.sin(t) ** 3)
        y = -(13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t))
        points.append((x, y))
    return points

# Hàm tạo cửa sổ nhỏ (popup)
def show_warm_tip(x, y, screen_width, screen_height):
    # Tạo một cửa sổ tkinter mới
    window = tk.Tk()
    
    window_width = 200
    window_height = 50
    
    # Tính tỉ lệ phóng to dựa trên kích thước màn hình
    scale = min(screen_width, screen_height) / 45 # Điều chỉnh số này để hình to/nhỏ (trong video là khoảng 40-60)
    
    # Tính toán vị trí đặt cửa sổ trên màn hình
    pos_x = int(screen_width / 2 + x * scale - window_width / 2)
    pos_y = int(screen_height / 2 + y * scale - window_height / 2)
    
    # Đảm bảo cửa sổ không trôi ra ngoài màn hình
    pos_x = max(0, min(pos_x, screen_width - window_width))
    pos_y = max(0, min(pos_y, screen_height - window_height))
    
    # Thiết lập vị trí và kích thước
    window.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")
    
    # Danh sách các lời chúc/thông điệp
    tips = [
        "Dream Comes True", 
        "Good Luck", 
        "Take a Break", 
        "Keep a Positive Mind", 
        "All Pain Is Temporary", 
        "Stay Calm",
        "See You Next",
        "Love You",
        "Be Happy"
    ]
    
    # Danh sách màu nền (tông hồng/tím)
    bg_colors = [
        'lightpink', 'mistyrose', 'lavender', 'salmon', 
        'plum', 'violet', 'orchid', 'thistle', 'hotpink'
    ]
    
    tip = random.choice(tips)
    bg = random.choice(bg_colors)
    
    # Tạo nhãn hiển thị chữ
    tk.Label(
        window, 
        text=tip, 
        bg=bg, 
        font=('Arial', 10, 'bold'), # Video dùng Microsoft YaHei, mình dùng Arial cho phổ biến
        width=25, 
        height=2
    ).pack()
    
    # Làm cửa sổ luôn nổi lên trên cùng
    window.attributes('-topmost', True)
    
    # Ẩn thanh tiêu đề (title bar) để đẹp hơn (giống video)
    window.overrideredirect(True)
    
    # Vòng lặp hiển thị cửa sổ
    window.mainloop()

def main():
    # Lấy kích thước màn hình hiện tại
    temp_window = tk.Tk()
    screen_width = temp_window.winfo_screenwidth()
    screen_height = temp_window.winfo_screenheight()
    temp_window.destroy() # Đóng cửa sổ tạm
    
    # Tạo danh sách tọa độ hình trái tim
    heart_points = generate_heart_points(60) # Số lượng cửa sổ (trong video khoảng 50-100)
    
    threads = []
    
    # Duyệt qua từng tọa độ và tạo luồng mới để mở cửa sổ
    for i, (x, y) in enumerate(heart_points):
        t = threading.Thread(target=show_warm_tip, args=(x, y, screen_width, screen_height))
        threads.append(t)
        t.start()
        
        # Thời gian nghỉ giữa các lần hiện cửa sổ để tạo hiệu ứng chạy vòng
        time.sleep(0.1) 

if __name__ == "__main__":
    main()
