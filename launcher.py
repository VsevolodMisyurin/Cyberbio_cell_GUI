import sys
import os

# 1. Определяем путь запуска
if getattr(sys, 'frozen', False):
    # Если запущено из EXE, берем путь к EXE
    base_dir = os.path.dirname(sys.executable)
else:
    # Если запущен скрипт, берем путь к скрипту
    base_dir = os.path.dirname(os.path.abspath(__file__))

# Добавляем путь в sys.path, чтобы Python видел внешние файлы
sys.path.insert(0, base_dir)

def start_app():
    try:
        # Импортируем наш основной GUI файл как модуль
        from gui_main import main
        # Запускаем функцию main() из gui_main.py
        main()
    except Exception as e:
        # Если что-то пошло не так, выводим ошибку (чтобы EXE не закрылся молча)
        import traceback
        with open("error_log.txt", "w") as f:
            traceback.print_exc(file=f)
        print(f"Критическая ошибка: {e}")
        input("Нажмите Enter для выхода...")

if __name__ == "__main__":
    start_app()