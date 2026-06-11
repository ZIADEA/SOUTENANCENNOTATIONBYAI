"""
Compile .po files to .mo files using polib (no gettext required).
Run: python compile_messages.py
"""
import pathlib
import polib

base = pathlib.Path(__file__).parent / 'locale'

for po_file in base.glob('*/LC_MESSAGES/django.po'):
    print(f'Compiling {po_file}...', end=' ')
    try:
        catalog = polib.pofile(str(po_file))
        mo_file = po_file.with_suffix('.mo')
        catalog.save_as_mofile(str(mo_file))
        print(f'OK -> {mo_file.name}  ({len(catalog)} entries)')
    except Exception as e:
        print(f'ERROR: {e}')

print('Done.')
