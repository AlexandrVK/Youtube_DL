import subprocess
import re

# Получить список тегов
result = subprocess.run(["git", "tag"], capture_output=True, text=True)
tags = result.stdout.strip().split("\n")

# Найти максимальный тег вида vX.Y.Z
version_re = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
versions = [
    tuple(map(int, version_re.match(tag).groups()))
    for tag in tags
    if version_re.match(tag)
]

if versions:
    last_version = max(versions)
    new_version = (last_version[0], last_version[1], last_version[2] + 1)
else:
    new_version = (1, 0, 0)

new_tag = f"v{new_version[0]}.{new_version[1]}.{new_version[2]}"

# Создать новый тег
git_tag = subprocess.run(["git", "tag", new_tag])
if git_tag.returncode != 0:
    print(f"Ошибка при создании тега {new_tag}")
    exit(1)

# Отправить тег на origin
git_push = subprocess.run(["git", "push", "origin", new_tag])
if git_push.returncode == 0:
    print(f"Создан и отправлен тег: {new_tag}")
    print("Через несколько минут появится новый релиз на GitHub!")
else:
    print(f"Ошибка при отправке тега {new_tag}")
