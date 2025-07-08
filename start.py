import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import yt_dlp
import threading
import re
import os
import sys
import datetime
import glob
import shutil

try:
    import winreg
except ImportError:
    winreg = None


# --- Функция для изменения даты создания файла на Windows через pywin32 ---
def set_creation_time_win(filepath, timestamp):
    if sys.platform == "win32":
        try:
            import pywintypes
            import win32file
            import win32con

            handle = win32file.CreateFile(
                filepath,
                win32con.GENERIC_WRITE,
                0,
                None,
                win32con.OPEN_EXISTING,
                win32con.FILE_ATTRIBUTE_NORMAL,
                None,
            )
            win32file.SetFileTime(
                handle,
                pywintypes.Time(timestamp),  # creation time
                None,  # last access time
                None,  # last write time
            )
            handle.close()
            return True
        except Exception as e:
            print(f"Ошибка при установке даты создания файла: {e}")
            return False
    return False


class YouTubeDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Downloader Enhanced")
        self.root.geometry("700x650")

        # Основные переменные
        self.url_var = tk.StringVar()
        self.quality_var = tk.StringVar(value="720p")
        self.format_var = tk.StringVar(value="mp4")
        self.codec_var = tk.StringVar(value="default")
        self.playlist_var = tk.BooleanVar(value=False)
        self.download_path = tk.StringVar(value=self.get_default_download_path())
        self._cancel_download = False
        self._current_temp_files = set()
        self._is_downloading = False

        self.create_widgets()
        self.download_path.trace_add("write", lambda *args: self.update_action_button())

    def get_default_download_path(self):
        # Попытка получить путь загрузок из реестра Windows
        if sys.platform == "win32" and winreg is not None:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders",
                ) as key:
                    downloads, _ = winreg.QueryValueEx(
                        key, "{374DE290-123F-4565-9164-39C4925E467B}"
                    )
                    # downloads может содержать переменные окружения
                    return os.path.expandvars(downloads)
            except Exception:
                pass
        # Fallback: стандартная папка загрузок
        return str(Path.home() / "Downloads")

    def create_widgets(self):
        # --- Кнопка проверки версии yt-dlp в правом верхнем углу ---
        self.version_frame = ttk.Frame(self.root)
        self.version_frame.place(relx=1.0, rely=0.0, anchor="ne")
        self.ytdlp_status_var = tk.StringVar(value="Проверка...")
        self.ytdlp_button = ttk.Button(
            self.version_frame,
            textvariable=self.ytdlp_status_var,
            command=self.update_ytdlp,
            state="disabled",
        )
        self.ytdlp_button.pack(padx=5, pady=2)
        self.check_ytdlp_version_async()

        # Поле ввода URL
        url_frame = ttk.Frame(self.root)
        url_frame.pack(pady=5, padx=10, anchor="w")
        ttk.Label(url_frame, text="YouTube URL:").pack(side=tk.LEFT, padx=(0, 5))
        self.url_button = ttk.Button(
            url_frame,
            text="Вставить",
            command=self.paste_from_clipboard,
            state="normal",
        )
        self.url_button.pack(side=tk.LEFT, padx=(0, 5))
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var, width=50)
        self.url_entry.pack(side=tk.LEFT)
        self.start_button = ttk.Button(
            url_frame, text="Старт", command=self.start_processing, state="disabled"
        )
        self.start_button.pack(side=tk.LEFT, padx=(5, 0))
        self.url_var.trace_add("write", self.on_url_var_change)
        self.update_url_button()

        # Сообщение-заглушка
        self.placeholder_label = ttk.Label(
            self.root, text="Введите адрес страницы с видео", font=("Arial", 16)
        )
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # Индикатор анализа
        self.analyze_frame = ttk.Frame(self.root)
        self.analyze_label = ttk.Label(
            self.analyze_frame, text="Анализирую видео...", font=("Arial", 16)
        )
        self.analyze_label.pack(pady=10)
        self.analyze_spinner = ttk.Progressbar(
            self.analyze_frame, mode="indeterminate", length=200
        )
        self.analyze_spinner.pack(pady=10)
        self.analyze_frame.pack_forget()

        # Блок быстрой закачки (Frame)
        self.quick_download_frame = ttk.Frame(self.root)

        # Выбор пути сохранения для быстрой закачки
        quick_path_frame = ttk.LabelFrame(
            self.quick_download_frame, text="Путь сохранения"
        )
        quick_path_frame.pack(pady=5, padx=10, fill="x")
        ttk.Entry(quick_path_frame, textvariable=self.download_path, width=50).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(quick_path_frame, text="Выбрать", command=self.select_path).pack(
            side=tk.LEFT
        )

        # Кнопки для быстрой закачки
        quick_buttons_frame = ttk.Frame(self.quick_download_frame)
        quick_buttons_frame.pack(pady=10)
        self.quick_buttons_frame = quick_buttons_frame  # Сохраняем ссылку

        self.quick_download_button = ttk.Button(
            quick_buttons_frame, text="Скачать", command=self.quick_download
        )
        self.quick_download_button.pack(side=tk.LEFT, padx=5)

        self.check_button = ttk.Button(
            quick_buttons_frame, text="Проверить", command=self.check_url_button
        )
        self.check_button.pack(side=tk.LEFT, padx=5)

        self.quick_delete_button = None  # Кнопка будет создаваться динамически

        # Метка для отображения информации о файле в быстрой закачке
        self.quick_filename_label = ttk.Label(self.quick_download_frame, text="")
        self.quick_filename_label.pack(pady=2)

        # Метка для отображения параметров файла закачки
        self.quick_file_params_label = ttk.Label(self.quick_download_frame, text="")
        self.quick_file_params_label.pack(pady=2)

        # Прогресс для быстрой закачки
        self.quick_progress_caption = ttk.Label(
            self.quick_download_frame, text="Текущий этап:"
        )
        self.quick_progress_caption.pack(pady=(5, 0))
        self.quick_progress_label = ttk.Label(self.quick_download_frame, text="")
        self.quick_progress_label.pack(pady=(1, 0))
        self.quick_progress = ttk.Progressbar(
            self.quick_download_frame, length=500, mode="determinate"
        )
        self.quick_progress.pack(pady=1)

        # Лог для быстрой закачки
        self.quick_log = tk.Text(self.quick_download_frame, height=10, width=80)
        self.quick_log.pack(pady=5)

        # Скрыть быструю закачку при запуске
        self.quick_download_frame.pack_forget()

        # Блок настроек (Frame)
        self.settings_frame = ttk.Frame(self.root)
        # Всё, что ниже, теперь добавляется в self.settings_frame, а не в self.root

        # Чекбокс для плейлистов
        ttk.Checkbutton(
            self.settings_frame, text="Скачать как плейлист", variable=self.playlist_var
        ).pack(pady=5)

        # Выбор пути сохранения
        path_frame = ttk.LabelFrame(self.settings_frame, text="Путь сохранения")
        path_frame.pack(pady=5, padx=10, fill="x")
        ttk.Entry(path_frame, textvariable=self.download_path, width=50).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(path_frame, text="Выбрать", command=self.select_path).pack(
            side=tk.LEFT
        )

        # Выбор качества
        quality_frame = ttk.LabelFrame(self.settings_frame, text="Качество видео")
        quality_frame.pack(pady=5, padx=10, fill="x")
        self.quality_options_label = ttk.Label(quality_frame, text="")
        self.quality_options_label.pack(anchor=tk.W, padx=5)
        self.quality_combobox = ttk.Combobox(
            quality_frame,
            textvariable=self.quality_var,
            values=["best"],
            state="readonly",
        )
        self.quality_combobox.pack(pady=5)

        # Выбор формата
        format_frame = ttk.LabelFrame(self.settings_frame, text="Формат")
        format_frame.pack(pady=5, padx=10, fill="x")
        self.format_options_label = ttk.Label(format_frame, text="mp4, webm, mkv")
        self.format_options_label.pack(anchor=tk.W, padx=5)
        formats = ["mp4", "webm", "mkv"]
        ttk.Combobox(
            format_frame, textvariable=self.format_var, values=formats, state="readonly"
        ).pack(pady=5)

        # Выбор кодека
        codec_frame = ttk.LabelFrame(self.settings_frame, text="Видео кодек")
        codec_frame.pack(pady=5, padx=10, fill="x")
        self.codec_options_label = ttk.Label(
            codec_frame, text="default, h264, h265, vp9, av1"
        )
        self.codec_options_label.pack(anchor=tk.W, padx=5)
        codecs = ["default", "h264", "h265", "vp9", "av1"]
        ttk.Combobox(
            codec_frame, textvariable=self.codec_var, values=codecs, state="readonly"
        ).pack(pady=5)

        # Поясняющая надпись к верхнему прогрессбару
        self.progress_caption = ttk.Label(self.settings_frame, text="Текущий этап:")
        self.progress_caption.pack(pady=(5, 0))
        self.progress_label = ttk.Label(self.settings_frame, text="")
        self.progress_label.pack(pady=(1, 0))
        self.progress = ttk.Progressbar(
            self.settings_frame, length=500, mode="determinate"
        )
        self.progress.pack(pady=1)
        # Поясняющая надпись к нижнему прогрессбару
        self.total_progress_caption = ttk.Label(
            self.settings_frame, text="Общий прогресс задачи:"
        )
        self.total_progress_caption.pack(pady=(5, 0))
        self.total_progress_label = ttk.Label(self.settings_frame, text="")
        self.total_progress_label.pack(pady=(1, 0))
        self.total_progress = ttk.Progressbar(
            self.settings_frame, length=500, mode="determinate"
        )
        self.total_progress.pack(pady=1)

        # Кнопка скачивания/проигрывания (универсальная)
        action_frame = ttk.Frame(self.settings_frame)
        action_frame.pack(pady=10)
        self.action_button = ttk.Button(
            action_frame, text="Скачать", command=self.start_download
        )
        self.action_button.pack(side=tk.LEFT, padx=5)
        self.delete_button = None  # Кнопка будет создаваться динамически
        # Метка для отображения имени файла
        self.filename_label = ttk.Label(self.settings_frame, text="")
        self.filename_label.pack(pady=2)
        # Лог
        self.log = tk.Text(self.settings_frame, height=10, width=80)
        self.log.pack(pady=5)
        # Периодическая проверка наличия файла
        self.root.after(2000, self.periodic_check_file)

        # Скрыть настройки при запуске
        self.settings_frame.pack_forget()

    def show_quick_download_interface(self):
        """Показывает интерфейс для быстрой закачки с настройками пути"""
        self.hide_analyze()
        self.placeholder_label.place_forget()

        # Показываем только блок с путем сохранения и кнопками
        self.quick_download_frame.pack(pady=5, fill="both", expand=True)

        # Обновляем информацию о файле
        self.update_quick_buttons()

    def show_placeholder(self):
        self.settings_frame.pack_forget()
        self.quick_download_frame.pack_forget()
        self.analyze_frame.pack_forget()
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    def show_analyze(self):
        self.settings_frame.pack_forget()
        self.quick_download_frame.pack_forget()
        self.placeholder_label.place_forget()
        self.analyze_frame.pack(pady=40)
        self.analyze_spinner.start(10)

    def hide_analyze(self):
        self.analyze_spinner.stop()
        self.analyze_frame.pack_forget()

    def show_settings(self):
        self.hide_analyze()
        self.quick_download_frame.pack_forget()
        self.placeholder_label.place_forget()
        self.settings_frame.pack(pady=5, fill="both", expand=True)
        self.update_action_button()

    def hide_settings(self):
        self.settings_frame.pack_forget()
        self.quick_download_frame.pack_forget()
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.hide_analyze()

    def select_path(self):
        path = filedialog.askdirectory(initialdir=self.download_path.get())
        if path:
            self.download_path.set(path)

    def log_message(self, message, important=True):
        if important:
            self.log.insert(tk.END, f"{message}\n")
            self.log.see(tk.END)
        # Убрано логирование в файл

    def progress_hook(self, d):
        # --- Этапы: downloading, merging, etc. ---
        # Отслеживаем временные файлы только для текущей загрузки
        fname = d.get("filename") or d.get("info_dict", {}).get("_filename")
        if fname and fname not in self._current_temp_files:
            self._current_temp_files.add(fname)
        status = d.get("status")
        if status == "downloading":
            p = d.get("_percent_str", "0%").replace("%", "")
            try:
                self.progress["value"] = float(p)
            except ValueError:
                pass
            stage = d.get("info_dict", {}).get("fragment_index")
            if d.get("info_dict", {}).get("requested_formats"):
                desc = (
                    d.get("info_dict", {})
                    .get("requested_formats")[0]
                    .get("format_note", "")
                )
                self.progress_label.config(text=f"Скачивание: {desc}")
            else:
                self.progress_label.config(text="Скачивание...")
        elif status == "finished":
            self.progress["value"] = 100
            self.progress_label.config(text="Скачивание завершено!")
            self.log_message("Скачивание завершено!", important=True)
        elif status == "merging":
            self.progress_label.config(text="Слияние аудио и видео...")
            self.progress["value"] = 100
        elif status == "error":
            self.progress_label.config(text="Ошибка!")
        else:
            self.progress_label.config(text=status or "Ожидание...")

    def get_format_string(self):
        quality = self.quality_var.get()
        codec = self.codec_var.get()

        if quality == "best":
            format_str = "bestvideo+bestaudio/best"
        else:
            height = quality.replace("p", "")
            if codec == "default":
                format_str = f"bestvideo[height<={height}]+bestaudio/best"
            else:
                format_str = (
                    f"bestvideo[height<={height}][vcodec~='{codec}']+bestaudio/best"
                )
        return format_str

    def get_output_filename(self, info=None):
        # Формирует имя файла без даты и времени и без id
        if info and info.get("title") and info.get("ext"):
            clean_title = self.clean_filename(info["title"])
            base = f"{clean_title}.{info['ext']}"
        else:
            base = "video.mp4"
        return os.path.join(self.download_path.get(), base)

    def download_video(self):
        url = self.url_var.get()
        if not url:
            messagebox.showerror("Ошибка", "Введите URL видео!")
            self.log_message("Введите URL видео!", important=True)
            return
        download_dir = self.download_path.get()
        if not os.path.exists(download_dir):
            try:
                os.makedirs(download_dir)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось создать папку: {e}")
                self.log_message(f"Ошибка создания папки: {e}", important=True)
                return
        # --- Новый блок: определяем, плейлист или нет ---
        is_playlist = self.playlist_var.get()
        entries_count = 1
        entries_urls = [url]
        if is_playlist:
            try:
                ydl_opts = {"quiet": True, "extract_flat": True, "skip_download": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                if "entries" in info and isinstance(info["entries"], list):
                    entries_count = len(info["entries"])
                    entries_urls = [
                        (
                            entry["url"]
                            if isinstance(entry, dict) and "url" in entry
                            else entry
                        )
                        for entry in info["entries"]
                    ]
            except Exception as e:
                self.log_message(f"Ошибка при анализе плейлиста: {e}", important=True)
                entries_count = 1
                entries_urls = [url]
        self.total_progress["maximum"] = entries_count
        self.total_progress["value"] = 0
        self.total_progress_label.config(text=f"Общий прогресс: 0 / {entries_count}")
        self.progress["value"] = 0
        self.progress_label.config(text="Ожидание...")
        self.root.update_idletasks()
        self._current_entry = 0
        self._entries_count = entries_count
        self._downloading_playlist = is_playlist and entries_count > 1
        self._playlist_urls = entries_urls
        self._playlist_results = []
        try:
            if self._downloading_playlist:
                for idx, entry_url in enumerate(entries_urls, 1):
                    self._current_entry = idx
                    self.root.after(
                        0,
                        lambda idx=idx: self.total_progress_label.config(
                            text=f"Общий прогресс: {idx-1} / {entries_count}"
                        ),
                    )
                    self.progress["value"] = 0
                    self.progress_label.config(text="Анализ...")
                    self.root.update_idletasks()
                    self._download_single_video(entry_url)
                    self.total_progress["value"] = idx
                self.total_progress_label.config(
                    text=f"Общий прогресс: {entries_count} / {entries_count}"
                )
            else:
                self._current_entry = 1
                self._download_single_video(url)
                self.total_progress["value"] = 1
                self.total_progress_label.config(text=f"Общий прогресс: 1 / 1")
        except Exception as e:
            self.log_message(f"{str(e)}", important=True)
            self.root.after(0, self.cleanup_temp_files)
        finally:
            self._is_downloading = False
            self.root.after(0, self.update_action_button)
            self.root.after(0, self.enable_url_buttons)  # Включаем кнопки URL обратно

    def _download_single_video(self, url):
        ydl_opts = {
            "format": self.get_format_string(),
            "outtmpl": os.path.join(self.download_path.get(), "%(title)s.%(ext)s"),
            "merge_output_format": self.format_var.get(),
            "progress_hooks": [self.progress_hook],
            "quiet": False,
            "noplaylist": True,
            "ffmpeg_location": "c:/Program Files (x86)/ffmpeg/bin/",
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                self.last_info = info
                filename_from_info = info.get("_filename")
                if filename_from_info and os.path.exists(filename_from_info):
                    self.last_downloaded_file = filename_from_info
                else:
                    title = info.get("title", "video").replace('"', "\uff02")
                    ext = info.get("ext", "mp4")
                    manual_filename = os.path.join(
                        self.download_path.get(), f"{title}.{ext}"
                    )
                    self.last_downloaded_file = manual_filename

                # --- Новый блок: смена даты файла и логика ---
                self.finalize_downloaded_file(self.last_info, self.log_message)

        except Exception as e:
            messagebox.showerror("Ошибка", f"Произошла ошибка: {str(e)}")
            self.log_message(f"Ошибка: {str(e)}", important=True)
        finally:
            self._is_downloading = False
            self.root.after(0, self.update_action_button)
            self.root.after(0, self.enable_url_buttons)  # Включаем кнопки URL обратно

    def cleanup_temp_files(self):
        # Удаляет только временные файлы, которые были созданы в этой сессии загрузки
        for f in self._current_temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        self.log_message("Временные файлы удалены.", important=True)
        self._current_temp_files.clear()

    def update_action_button(self):
        info = getattr(self, "last_info", None)
        filename = self.get_real_downloaded_file(info)
        if not filename:
            filename = getattr(self, "last_downloaded_file", None)
        if filename:
            self.filename_label.config(text=f"Файл: {filename}")
        else:
            self.filename_label.config(text="")
        if filename and os.path.exists(filename):
            self.last_downloaded_file = filename
            self.action_button.config(
                text="Проиграть скачанный файл",
                command=self.play_downloaded_file,
                state="normal",
            )
            if self.delete_button is None:
                action_frame = self.action_button.master
                self.delete_button = ttk.Button(
                    action_frame, text="Удалить", command=self.delete_downloaded_file
                )
                self.delete_button.pack(side=tk.LEFT, padx=5)
        else:
            state = "normal" if not self._is_downloading else "disabled"
            self.action_button.config(
                text="Скачать", command=self.start_download, state=state
            )
            if self.delete_button is not None:
                self.delete_button.destroy()
                self.delete_button = None

    def periodic_check_file(self):
        self.update_action_button()
        self.update_quick_buttons()
        self.root.after(2000, self.periodic_check_file)

    def _process_url_change(self, url):
        """Обрабатывает URL после нажатия кнопки Старт"""
        if not url:
            messagebox.showerror("Ошибка", "Введите URL видео!")
            return

        # Проверяем, является ли это валидной YouTube ссылкой или ID
        is_valid_url = self.is_youtube_url(url)
        is_valid_id = self.is_youtube_id(url)

        if not is_valid_url and not is_valid_id:
            messagebox.showerror("Ошибка", "Это не ссылка на YouTube видео!")
            return

        # Сбрасываем состояние при новом адресе
        self._is_downloading = False
        self.enable_url_buttons()
        self.show_placeholder()  # Сбрасываем интерфейс

        # Очищаем информацию о последнем скачанном файле
        if hasattr(self, "last_downloaded_file"):
            delattr(self, "last_downloaded_file")
        if hasattr(self, "last_info"):
            delattr(self, "last_info")

        # Сбрасываем состояние кнопок быстрой закачки
        if hasattr(self, "quick_download_button"):
            self.quick_download_button.config(
                text="Скачать", command=self.quick_download, state="normal"
            )
        if hasattr(self, "check_button"):
            self.check_button.config(state="normal")
        # Сбрасываем информацию о файле в быстрой закачке
        if hasattr(self, "quick_filename_label"):
            self.quick_filename_label.config(text="")
        if hasattr(self, "quick_file_params_label"):
            self.quick_file_params_label.config(text="")

        # Сбрасываем состояние кнопки в полном интерфейсе
        if hasattr(self, "action_button"):
            self.action_button.config(
                text="Скачать", command=self.start_download, state="normal"
            )

        # Если это ID - проверяем существование
        if is_valid_id:
            self.progress_label.config(text="Проверка id...")
            self.root.update_idletasks()

            def check_id():
                exists = self.check_youtube_id_exists(url)
                if exists:
                    full_url = f"https://www.youtube.com/watch?v={url}"
                    self.url_var.set(full_url)
                    self.show_quick_download_interface()
                else:
                    self.log_message("Видео с таким id не найдено", important=True)
                    self.show_placeholder()

            threading.Thread(target=check_id, daemon=True).start()
            return

        # Если это валидная ссылка - сразу показываем интерфейс быстрой закачки
        if is_valid_url:
            self.show_quick_download_interface()
            return

    def check_url_button(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Ошибка", "Введите URL видео!")
            self.show_placeholder()
            return
        if not self.is_youtube_url(url):
            messagebox.showerror("Ошибка", "Это не ссылка на YouTube видео!")
            self.show_placeholder()
            return
        self.disable_url_buttons()  # Отключаем кнопки URL во время анализа
        self.show_analyze()
        threading.Thread(
            target=self.analyze_and_update, args=(url,), daemon=True
        ).start()

    def analyze_and_update(self, url):
        try:
            ydl_opts = {"quiet": True, "skip_download": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            self.last_info = info  # Сохраняем info для дальнейшего использования
            # --- Проверка наличия файла после анализа ---
            filename1 = self.get_real_downloaded_file(self.last_info)
            filename2 = self.get_expected_filename(self.last_info)
            filename = filename1 if filename1 and os.path.exists(filename1) else None
            if not filename and filename2 and os.path.exists(filename2):
                filename = filename2
            if filename and os.path.exists(filename):
                self.last_downloaded_file = filename
            self.update_qualities_from_url(url)
            self.root.after(0, self.show_settings)
            self.root.after(0, lambda: self.log_message("Анализ завершён успешно!"))
            self.root.after(0, self.update_action_button)
            self.root.after(0, self.enable_url_buttons)  # Включаем кнопки URL обратно
        except Exception as e:
            self.log_message(f"Ошибка при анализе: {e}")
            self.root.after(0, self.show_placeholder)
            self.root.after(0, self.update_action_button)
            self.root.after(0, self.enable_url_buttons)  # Включаем кнопки URL обратно

    def update_qualities_from_url(self, url):
        self.log_message("Получение доступных разрешений...")
        try:
            ydl_opts = {"quiet": True, "skip_download": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            formats = info.get("formats", [])
            heights = set()
            for f in formats:
                if f.get("vcodec", "none") != "none" and f.get("height"):
                    heights.add(f["height"])
            qualities = sorted(
                [f"{h}p" for h in heights if h], key=lambda x: int(x[:-1]), reverse=True
            )
            if not qualities:
                qualities = ["best"]
            else:
                qualities = ["best"] + qualities
            # Обновление комбобокса в главном потоке
            self.root.after(0, self.set_quality_options, qualities)
        except Exception as e:
            self.log_message(f"Ошибка при получении разрешений: {e}")
            self.root.after(0, self.set_quality_options, ["best"])

    def set_quality_options(self, qualities):
        self.quality_combobox["values"] = qualities
        self.quality_options_label.config(text=", ".join(qualities))
        # По умолчанию 720p, если есть, иначе максимальное доступное
        if "720p" in qualities:
            self.quality_var.set("720p")
        else:
            self.quality_var.set(qualities[0])

    def is_youtube_url(self, url):
        # Простейшая проверка на youtube-ссылку
        pattern = r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/"
        result = re.match(pattern, url, re.IGNORECASE) is not None
        return result

    def is_youtube_id(self, text):
        # Проверка на id видео (11 символов, буквы/цифры/-, _)
        return bool(re.match(r"^[A-Za-z0-9_-]{11}$", text.strip()))

    def check_youtube_id_exists(self, video_id):
        import urllib.request

        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            with urllib.request.urlopen(url) as resp:
                return resp.status == 200
        except Exception:
            return False

    def update_url_button(self, *args):
        # Кнопка "Вставить" всегда активна, кроме моментов закачки/анализа
        if hasattr(self, "_is_downloading") and self._is_downloading:
            self.url_button.config(state="disabled")
            self.start_button.config(state="disabled")
        else:
            self.url_button.config(state="normal")
            # Проверяем валидность URL для кнопки Старт
            url = self.url_var.get().strip()
            is_valid_url = self.is_youtube_url(url)
            is_valid_id = self.is_youtube_id(url)

            if is_valid_url or is_valid_id:
                self.start_button.config(state="normal")
            else:
                self.start_button.config(state="disabled")

    def paste_from_clipboard(self):
        try:
            clipboard = self.root.clipboard_get()
            self.url_var.set(clipboard)
            self.url_entry.icursor(tk.END)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось вставить из буфера обмена: {e}")

    def play_downloaded_file(self):
        filename = getattr(self, "last_downloaded_file", None)
        if filename and os.path.exists(filename):
            try:
                if sys.platform == "win32":
                    import subprocess

                    subprocess.Popen(["start", "", filename], shell=True)
                elif sys.platform == "darwin":
                    os.system(f'open "{filename}"')
                else:
                    os.system(f'xdg-open "{filename}"')
                self.log_message("Файл воспроизводится...", important=True)
            except Exception as e:
                self.log_message(f"Не удалось открыть файл: {e}", important=True)
                messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")
        else:
            self.log_message("Файл не найден!", important=True)
            messagebox.showerror("Ошибка", "Файл не найден!")

    def start_download(self):
        url = self.url_var.get().strip()
        self.progress["value"] = 0
        self.log.delete(1.0, tk.END)
        self._cancel_download = False
        self._current_temp_files = set()
        self._is_downloading = True
        self.action_button.config(state="disabled")
        self.disable_url_buttons()  # Отключаем кнопки URL во время закачки
        self.root.update_idletasks()
        # Блокируем повторный запуск, если поток уже идёт
        if (
            hasattr(self, "_download_thread")
            and self._download_thread
            and self._download_thread.is_alive()
        ):
            return
        self._download_thread = threading.Thread(target=self.download_video)
        self._download_thread.start()

    def delete_downloaded_file(self):
        filename = getattr(self, "last_downloaded_file", None)
        if filename and os.path.exists(filename):
            answer = messagebox.askyesno("Удалить файл", f"Удалить файл?\n{filename}")
            if answer:
                try:
                    os.remove(filename)
                    self.log_message("Файл удалён.", important=True)
                    self.update_action_button()
                except Exception as e:
                    self.log_message(f"Ошибка при удалении файла: {e}", important=True)
                    messagebox.showerror("Ошибка", f"Ошибка при удалении файла: {e}")
        else:
            self.log_message("Файл не найден для удаления!", important=True)
            messagebox.showerror("Ошибка", "Файл не найден для удаления!")

    # --- Проверка и обновление yt-dlp ---
    def check_ytdlp_version_async(self):
        threading.Thread(target=self.check_ytdlp_version, daemon=True).start()

    def check_ytdlp_version(self):
        try:
            import subprocess
            import pkg_resources

            current = pkg_resources.get_distribution("yt-dlp").version
            import urllib.request, json

            with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json") as resp:
                data = json.load(resp)
                latest = data["info"]["version"]
            if current == latest:
                self.root.after(0, lambda: self.set_ytdlp_status("Актуально", False))
            else:
                self.root.after(0, lambda: self.set_ytdlp_status("Обновить", True))
        except Exception as e:
            self.root.after(0, lambda: self.set_ytdlp_status("Ошибка", False))

    def set_ytdlp_status(self, text, can_update):
        self.ytdlp_status_var.set(text)
        self.ytdlp_button.config(state="normal" if can_update else "disabled")

    def update_ytdlp(self):
        self.ytdlp_status_var.set("Обновление...")
        self.ytdlp_button.config(state="disabled")
        threading.Thread(target=self._update_ytdlp_thread, daemon=True).start()

    def _update_ytdlp_thread(self):
        try:
            import subprocess

            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
            )
            self.root.after(
                0,
                lambda: self.set_ytdlp_status("yt-dlp обновлён! Перезапуск...", False),
            )
            import os
            import sys

            # Перезапуск приложения сразу
            os.execl(sys.executable, sys.executable, *sys.argv)
        except Exception as e:
            self.root.after(
                0, lambda: self.set_ytdlp_status("Ошибка обновления", False)
            )
        self.check_ytdlp_version_async()

    def disable_url_buttons(self):
        """Делает кнопки "Вставить", "Старт" и поле ввода неактивными"""
        self.url_button.config(state="disabled")
        self.url_entry.config(state="disabled")
        self.start_button.config(state="disabled")

    def enable_url_buttons(self):
        """Делает кнопки "Вставить", "Старт" и поле ввода активными"""
        self.url_button.config(state="normal")
        self.url_entry.config(state="normal")
        self.start_button.config(state="normal")

    def quick_download(self):
        """Быстрая закачка с параметрами по умолчанию"""
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Ошибка", "Введите URL видео!")
            return

        download_dir = self.download_path.get()
        if not os.path.exists(download_dir):
            try:
                os.makedirs(download_dir)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось создать папку: {e}")
                return

        # --- Блокируем кнопки и очищаем лог до скачивания ---
        self.quick_progress["value"] = 0
        self.quick_log.delete(1.0, tk.END)
        if hasattr(self, "quick_file_params_label"):
            self.quick_file_params_label.config(text="")
        self._cancel_download = False
        self._current_temp_files = set()
        self._is_downloading = True
        self.quick_download_button.config(state="disabled")
        self.check_button.config(state="disabled")
        self.disable_url_buttons()  # Делаем кнопки URL неактивными
        self.root.update_idletasks()

        # --- Запускаем скачивание сразу в отдельном потоке ---
        if (
            hasattr(self, "_quick_download_thread")
            and self._quick_download_thread
            and self._quick_download_thread.is_alive()
        ):
            return

        self._quick_download_thread = threading.Thread(
            target=self._quick_download_video
        )
        self._quick_download_thread.start()

    def _quick_download_video(self):
        url = self.url_var.get().strip()
        ydl_opts = {
            "format": "best",  # Лучшее качество по умолчанию
            "outtmpl": os.path.join(self.download_path.get(), "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",  # MP4 по умолчанию
            "progress_hooks": [self.quick_progress_hook],
            "quiet": False,
            "noplaylist": True,
            "ffmpeg_location": "c:/Program Files (x86)/ffmpeg/bin/",
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                self.last_info = info
                filename_from_info = info.get("_filename")
                if filename_from_info and os.path.exists(filename_from_info):
                    self.last_downloaded_file = filename_from_info
                else:
                    title = info.get("title", "video").replace('"', "\uff02")
                    ext = info.get("ext", "mp4")
                    manual_filename = os.path.join(
                        self.download_path.get(), f"{title}.{ext}"
                    )
                    self.last_downloaded_file = manual_filename

                # --- Новый блок: смена даты файла и логика ---
                self.finalize_downloaded_file(self.last_info, self.quick_log_message)

        except Exception as e:
            messagebox.showerror("Ошибка", f"Произошла ошибка: {str(e)}")
        finally:
            info = getattr(self, "last_info", None)
            filename = self.get_real_downloaded_file(info)
            if filename and os.path.exists(filename):
                self.last_downloaded_file = filename
                self.root.after(0, self.update_quick_buttons)
            self._is_downloading = False
            self.root.after(0, self.enable_url_buttons)  # Включаем кнопки URL обратно

    def quick_progress_hook(self, d):
        """Обработчик прогресса для быстрой закачки"""
        # Отслеживаем временные файлы только для текущей загрузки
        fname = d.get("filename") or d.get("info_dict", {}).get("_filename")
        if fname and fname not in self._current_temp_files:
            self._current_temp_files.add(fname)

        status = d.get("status")
        if status == "downloading":
            p = d.get("_percent_str", "0%").replace("%", "")
            try:
                self.quick_progress["value"] = float(p)
            except ValueError:
                pass

            # Получаем информацию о параметрах закачки
            format_info = d.get("info_dict", {})
            height = format_info.get("height")
            width = format_info.get("width")
            vcodec = format_info.get("vcodec")
            filesize = format_info.get("filesize")

            # Если нет информации в info_dict, пробуем получить из других источников
            if not height and not width:
                requested_formats = format_info.get("requested_formats", [])
                if requested_formats:
                    video_format = requested_formats[0]
                    height = video_format.get("height")
                    width = video_format.get("width")
                    vcodec = video_format.get("vcodec")
                    filesize = video_format.get("filesize")

            # Показываем параметры пользователю в отдельной метке
            if height and width:
                params_text = f"Параметры: {width}x{height}, кодек: {vcodec}"
                if filesize:
                    size_mb = filesize / (1024 * 1024)
                    params_text += f", размер: {size_mb:.1f} MB"
                self.quick_file_params_label.config(text=params_text)
                self.quick_progress_label.config(text="Скачивание...")
            else:
                self.quick_progress_label.config(text="Скачивание...")

        elif status == "finished":
            self.quick_progress["value"] = 100
            self.quick_progress_label.config(text="Скачивание завершено!")

        elif status == "merging":
            self.quick_progress_label.config(text="Слияние аудио и видео...")
            self.quick_progress["value"] = 100
        elif status == "error":
            self.quick_progress_label.config(text="Ошибка!")
        else:
            self.quick_progress_label.config(text=status or "Ожидание...")

    def update_quick_buttons(self):
        """Обновляет состояние кнопок быстрой закачки"""
        info = getattr(self, "last_info", None)
        filename = self.get_real_downloaded_file(info)
        if filename:
            self.quick_filename_label.config(text=f"Файл: {filename}")
        else:
            self.quick_filename_label.config(text="")

        # Управляем кнопками
        if filename and os.path.exists(filename):
            self.last_downloaded_file = filename
            self.quick_download_button.config(
                text="Проиграть скачанный файл",
                command=self.play_downloaded_file,
                state="normal",
            )
            # Показываем кнопку "Удалить"
            if self.quick_delete_button is None:
                self.quick_delete_button = ttk.Button(
                    self.quick_buttons_frame,
                    text="Удалить",
                    command=self.delete_downloaded_file,
                )
                self.quick_delete_button.pack(side=tk.LEFT, padx=5)
        else:
            # Кнопки активны только если не идёт загрузка
            state = "normal" if not self._is_downloading else "disabled"
            self.quick_download_button.config(
                text="Скачать", command=self.quick_download, state=state
            )
            self.check_button.config(state=state)
            # Скрываем кнопку "Удалить"
            if self.quick_delete_button is not None:
                self.quick_delete_button.destroy()
                self.quick_delete_button = None

    def start_processing(self):
        self._process_url_change(self.url_var.get().strip())

    def on_url_var_change(self, *args):
        self.update_url_button()

    def clean_filename(self, filename):
        from yt_dlp.utils import sanitize_filename

        return sanitize_filename(filename, restricted=False)

    def finalize_downloaded_file(self, info, log_func):
        filename = self.get_real_downloaded_file(info)
        if filename and os.path.exists(filename):
            if self.set_file_current_time(filename):
                log_func(
                    f"Дата файла установлена: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
                    important=True,
                )
            else:
                log_func("Не удалось изменить дату файла!", important=True)
        else:
            log_func("Файл не найден для изменения даты!", important=True)

    def get_file_info_before_download(self, url):
        """Получает информацию о файле перед закачкой"""
        try:
            ydl_opts = {
                "format": "best",
                "quiet": True,
                "skip_download": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get("title", "video")
                clean_title = self.clean_filename(title)
                ext = info.get("ext", "mp4")
                filename = os.path.join(
                    self.download_path.get(), f"{clean_title}.{ext}"
                )
                return filename, info
        except Exception as e:
            return None, None

    def get_real_downloaded_file(self, info):
        if not info:
            return None
        rd = info.get("requested_downloads")
        if rd and isinstance(rd, list) and len(rd) > 0:
            return (
                rd[0].get("filepath") or rd[0].get("filename") or rd[0].get("_filename")
            )
        return None

    def set_file_current_time(self, filepath):
        import datetime, os, sys

        if not filepath or not os.path.exists(filepath):
            return False
        try:
            now = datetime.datetime.now().timestamp()
            os.utime(filepath, (now, now))
            if sys.platform == "win32":
                set_creation_time_win(filepath, now)
            return True
        except Exception as e:
            return False

    def get_expected_filename(self, info):
        import os

        if not info:
            return None
        title = self.clean_filename(info.get("title", "video"))
        ext = info.get("ext", "mp4")
        return os.path.join(self.download_path.get(), f"{title}.{ext}")

    def quick_log_message(self, message, important=True):
        self.quick_log.insert(tk.END, f"{message}\n")
        self.quick_log.see(tk.END)


# --- Проверка наличия ffmpeg ---
def check_ffmpeg_exists():
    import subprocess

    try:
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(["ffmpeg", "-version"], **kwargs)
        return result.returncode == 0
    except Exception:
        return False


# --- Автоустановка ffmpeg ---
def try_install_ffmpeg():
    import platform
    import subprocess

    system = platform.system().lower()
    try:
        if system == "windows":
            if shutil.which("winget"):
                result = subprocess.run(
                    [
                        "winget",
                        "install",
                        "--id=Gyan.FFmpeg",
                        "--source=winget",
                        "--accept-package-agreements",
                        "--accept-source-agreements",
                    ],
                    check=True,
                )
                return result.returncode == 0
            else:
                return False
        elif system == "linux":
            if shutil.which("apt"):
                subprocess.run(["sudo", "apt", "update"], check=True)
                result = subprocess.run(
                    ["sudo", "apt", "install", "-y", "ffmpeg"], check=True
                )
                return result.returncode == 0
            else:
                return False
        elif system == "darwin":
            if shutil.which("brew"):
                result = subprocess.run(["brew", "install", "ffmpeg"], check=True)
                return result.returncode == 0
            else:
                return False
        else:
            return False
    except Exception:
        return False


# --- Инструкция по ручной установке ffmpeg ---
def show_ffmpeg_manual():
    import platform

    system = platform.system().lower()
    if system == "windows":
        msg = (
            "На вашем компьютере не найден ffmpeg!\n\n"
            "Пожалуйста, скачайте и установите ffmpeg с официального сайта:\n"
            "https://ffmpeg.org/download.html\n\n"
            "Рекомендуется использовать winget: winget install --id=Gyan.FFmpeg --source=winget\n"
            "После установки убедитесь, что ffmpeg добавлен в PATH или находится по пути c:/Program Files (x86)/ffmpeg/bin/ffmpeg.exe."
        )
    elif system == "linux":
        msg = (
            "На вашем компьютере не найден ffmpeg!\n\n"
            "Для Ubuntu/Debian выполните в терминале:\n"
            "sudo apt update && sudo apt install ffmpeg -y\n\n"
            "Для других дистрибутивов смотрите инструкции на https://ffmpeg.org/download.html"
        )
    elif system == "darwin":
        msg = (
            "На вашем компьютере не найден ffmpeg!\n\n"
            "Для установки через Homebrew выполните в терминале:\n"
            "brew install ffmpeg\n\n"
            'Если Homebrew не установлен: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"\n'
            "Подробнее: https://ffmpeg.org/download.html"
        )
    else:
        msg = (
            "На вашей системе не найден ffmpeg!\n\n"
            "Пожалуйста, скачайте и установите ffmpeg с https://ffmpeg.org/download.html"
        )
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("FFmpeg не найден", msg)


# --- Точка входа ---
def main():
    if not check_ffmpeg_exists():
        root = tk.Tk()
        root.withdraw()
        answer = messagebox.askyesno(
            "FFmpeg не найден",
            "На вашем компьютере не найден ffmpeg!\n\n"
            "Хотите попробовать установить ffmpeg автоматически?",
        )
        if answer:
            ok = try_install_ffmpeg()
            if ok and check_ffmpeg_exists():
                messagebox.showinfo(
                    "FFmpeg установлен",
                    "FFmpeg успешно установлен! Программа продолжит работу.",
                )
            else:
                show_ffmpeg_manual()
                sys.exit(1)
        else:
            show_ffmpeg_manual()
            sys.exit(1)
    root = tk.Tk()
    app = YouTubeDownloader(root)
    root.mainloop()


if __name__ == "__main__":
    main()
