from PIL import Image, ImageDraw, ImageFont
import os


def create_icon():
    # Создаем изображение 256x256 пикселей
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Рисуем фон (круг с градиентом)
    center = size // 2
    radius = size // 2 - 10

    # Градиент от синего к фиолетовому
    for i in range(radius):
        alpha = int(255 * (1 - i / radius))
        color = (50, 100, 200, alpha)
        draw.ellipse(
            [center - i, center - i, center + i, center + i], fill=color, outline=None
        )

    # Рисуем символ YouTube (красный треугольник)
    triangle_points = [
        (center - 40, center - 30),
        (center - 40, center + 30),
        (center + 40, center),
    ]
    draw.polygon(triangle_points, fill=(255, 0, 0, 255))

    # Добавляем текст "DL"
    try:
        # Попробуем использовать системный шрифт
        font = ImageFont.truetype("arial.ttf", 60)
    except:
        # Fallback на стандартный шрифт
        font = ImageFont.load_default()

    text = "DL"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = center - text_width // 2
    y = center + 50
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    # Сохраняем в разных форматах
    img.save("icon.png")
    img.save(
        "icon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    print("Иконки созданы: icon.png и icon.ico")


if __name__ == "__main__":
    create_icon()
