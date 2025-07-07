# pip install pillow
from PIL import Image

input_png = "icon.png"  # Ваш PNG 1024x1024
output_ico = "icon.ico"

sizes = [16, 32, 48, 64, 128, 256]

img = Image.open(input_png)
img.save(output_ico, format="ICO", sizes=[(size, size) for size in sizes])

print(f"Создан файл {output_ico} с размерами: {sizes}")
