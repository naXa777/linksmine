import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'linksmine'
if not SOURCE.is_file():
    SOURCE = HERE / 'linksmine'
loader = importlib.machinery.SourceFileLoader('linksmine_app', str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
app = importlib.util.module_from_spec(spec)
loader.exec_module(app)

BASE = 'remember_last_entry: yes\n'
RAW = b'\x07\x00\x00\x00Windows\x00'
IDENT = 'a' * 32

def menu(body):
    return app.parse_menu(BASE + body)

class MenuTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(menu('/Windows\nprotocol: efi\n'), [{'title':'Windows','path':'Windows'}])
    def test_directory_not_bootable(self):
        self.assertEqual(menu('/+Linux\n//Arch\nprotocol: linux\n')[0]['path'], 'Linux/Arch')
    def test_skip_level(self):
        with self.assertRaises(ValueError): menu('///Arch\nprotocol: linux\n')
    def test_multiple_roots(self):
        self.assertEqual([e['path'] for e in menu('/+OS\n//Arch\nprotocol: linux\n/Windows\nprotocol: efi\n')], ['OS/Arch','Windows'])
    def test_duplicates(self):
        self.assertEqual([e['path'] for e in menu('/Windows\nprotocol: efi\n/Windows\nprotocol: efi\n')], ['Windows','Windows#1'])
    def test_duplicate_directories(self):
        self.assertEqual([e['path'] for e in menu('/OS\n//Linux\nprotocol: linux\n/OS\n//Linux\nprotocol: linux\n')], ['OS/Linux','OS#1/Linux'])
    def test_literal_path_characters(self):
        self.assertEqual(menu('/A/B#C\\D\nprotocol: linux\n')[0]['path'], r'A\/B\#C\\D')
    def test_unicode(self):
        self.assertEqual(menu('/Lietuvių\nprotocol: linux\n')[0]['title'], 'Lietuvių')
    def test_macros_rejected_in_titles(self):
        with self.assertRaises(ValueError): menu('/${OS}\nprotocol: linux\n')
    def test_macro_definitions_and_cmdline_allowed(self):
        self.assertEqual(len(menu('${ROOT}=abc\n/Arch\nprotocol: linux\ncmdline: root=${ROOT}\n')), 1)
    def test_global_case(self):
        self.assertEqual(len(app.parse_menu('REMEMBER_LAST_ENTRY: yes\n/A\nPROTOCOL: linux\n')), 1)
    def test_remember_missing(self):
        with self.assertRaises(ValueError): app.parse_menu('/A\nprotocol: linux\n')
    def test_remember_local(self):
        with self.assertRaises(ValueError): app.parse_menu('/A\nremember_last_entry: yes\nprotocol: linux\n')
    def test_remember_no(self):
        with self.assertRaises(ValueError): app.parse_menu('remember_last_entry: no\n/A\nprotocol: linux\n')
    def test_bios_filtered(self):
        paths = menu('/Old\nprotocol: bios\n/Windows\nprotocol: efi\n')
        self.assertEqual(len(paths), 1)
    def test_firmware_condition(self):
        self.assertEqual(len(menu('/Old\nprotocol: linux\nif_fw_type: BIOS\n/New\nprotocol: linux\n')), 1)
    def test_parent_condition(self):
        self.assertEqual(len(menu('/Old\nif_fw_type: BIOS\n//Child\nprotocol: linux\n/New\nprotocol: linux\n')), 1)
    def test_arch_condition(self):
        self.assertEqual(len(menu('/ARM\nprotocol: linux\nif_arch: aarch64\n/PC\nprotocol: linux\nif_arch: x86-64 aarch64\n')), 1)
    def test_no_protocol_not_bootable(self):
        with self.assertRaises(ValueError): menu('/Folder\ncomment: not bootable\n')
    def test_comments(self):
        self.assertEqual(len(menu('# /ignored\n/A\n# a comment\nprotocol: linux\n')), 1)
    def test_control_title(self):
        with self.assertRaises(ValueError): menu('/A\tB\nprotocol: linux\n')

class FirmwareTests(unittest.TestCase):
    def test_decode(self): self.assertEqual(app.decode(RAW), 'Windows')
    def test_utf8(self): self.assertEqual(app.decode(RAW[:4] + 'Žaidimai'.encode() + b'\0'), 'Žaidimai')
    def test_preserve_attributes(self): self.assertEqual(app.payload(RAW, 'OS/Linux'), RAW[:4]+b'OS/Linux\0')
    def test_wrong_attributes(self):
        with self.assertRaises(ValueError): app.decode(b'\x06\0\0\0Windows\0')
    def test_missing_terminator(self):
        with self.assertRaises(ValueError): app.decode(RAW[:-1])
    def test_embedded_nul(self):
        with self.assertRaises(ValueError): app.decode(RAW[:4]+b'Win\0dows\0')
    def test_empty(self):
        with self.assertRaises(ValueError): app.decode(RAW[:4]+b'\0')
    def test_numeric_old_format(self):
        with self.assertRaises(ValueError): app.decode(RAW[:4]+b'\x02\0')
    def test_large_payload(self):
        with self.assertRaises(ValueError): app.payload(RAW, 'a'*4097)
    def test_newline_payload(self):
        with self.assertRaises(ValueError): app.payload(RAW, 'Windows\nExec=bad')
    def test_non_utf8(self):
        with self.assertRaises(UnicodeError): app.decode(RAW[:4]+b'\xff\0')
    def test_variable_name_no_personal_guid(self):
        self.assertTrue(app.VARIABLE_RE.fullmatch('LimineLastBootedEntry-11111111-2222-3333-4444-555555555555'))
    def test_variable_traversal(self):
        with self.assertRaises(ValueError):
            with app.open_variable('../../etc/passwd'): pass
    def test_discovery_skips_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            names = ['LimineLastBootedEntry-11111111-2222-3333-4444-555555555555',
                     'LimineLastBootedEntry-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee']
            for name in names: (base/name).touch()
            with patch.object(app, 'EFIVARS', base), patch.object(app, 'read_variable', side_effect=[RAW,b'bad']):
                items=app.discover_variables()
                self.assertEqual(items[0]['current'], 'Windows')
                self.assertIn('error', items[1])

class SafetyTests(unittest.TestCase):
    def test_id(self): self.assertEqual(app.valid_id(IDENT), IDENT)
    def test_id_traversal(self):
        with self.assertRaises(ValueError): app.valid_id('../etc/passwd')
    def test_label_empty(self):
        with self.assertRaises(ValueError): app.checked_text('   ')
    def test_label_control(self):
        with self.assertRaises(ValueError): app.desktop_text('Windows\nExec=bad', IDENT)
    def test_label_not_command(self):
        content=app.desktop_text('Windows; $(touch /tmp/bad) %F', IDENT)
        self.assertIn(f'Exec=/usr/bin/linksmine reboot {IDENT}\n', content)
        self.assertEqual(content.count('\nExec='),1)
    def test_desktop_backslash(self):
        self.assertIn('Name=A\\\\B\n', app.desktop_text('A\\B', IDENT))
    def test_atomic_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config'
            app.atomic_file(path,b'one',0o600)
            app.atomic_file(path,b'two',0o644)
            self.assertEqual(path.read_bytes(),b'two')
            self.assertEqual(path.stat().st_mode & 0o777,0o644)
            self.assertEqual(len(list(Path(tmp).iterdir())),1)
    def test_owner_mismatch(self):
        with patch.dict(os.environ, {'SUDO_UID':'1001'}):
            with self.assertRaises(ValueError): app.authorize_config({'uid':1000})
    def test_matching_owner(self):
        with patch.dict(os.environ, {'SUDO_UID':'1000'}): app.authorize_config({'uid':1000})
    def test_nonroot_helper(self):
        with patch.object(os, 'geteuid', return_value=1000):
            with self.assertRaises(ValueError): app.root_only()
    def test_kde(self):
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP':'KDE'}): app.require_kde()
    def test_other_desktop(self):
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP':'GNOME'}):
            with self.assertRaises(ValueError): app.require_kde()
    def test_editable_label(self):
        with patch('builtins.input', return_value='Play games'), patch.object(app.readline, 'set_startup_hook'):
            self.assertEqual(app.edit_label('Reboot into Windows'),'Play games')


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            'entry': 'Linux',
            'menu': '/boot/limine.conf',
            'variable': (
                'LimineLastBootedEntry-'
                '03884334-1756-4978-9c8c-86fb8998b4ea'
            ),
            'uid': 1000,
        }
        self.patches = [patch.object(app,'locked',side_effect=lambda: __import__('contextlib').nullcontext()),
                        patch.object(app,'load_config',return_value=self.data),
                        patch.object(app,'authorize_config'),
                        patch.object(app,'read_menu',return_value=[{'path':'Linux'}])]
        for p in self.patches: p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
    def test_unchanged_value_not_written(self):
        raw = RAW[:4] + b'Linux\0'
        with patch.object(app,'read_variable',return_value=raw), patch.object(app,'open_variable') as op:
            app.select(IDENT)
            op.assert_not_called()
    def test_removed_entry_never_written(self):
        with patch.object(app,'read_menu',return_value=[]), patch.object(app,'read_variable') as read:
            with self.assertRaises(ValueError): app.select(IDENT)
            read.assert_not_called()
    def test_immutable_restored_on_write_failure(self):
        @__import__('contextlib').contextmanager
        def opened(*args): yield 42
        with patch.object(app,'read_variable',return_value=RAW), patch.object(app,'open_variable',side_effect=opened), patch.object(app.fcntl,'ioctl',return_value=(16).to_bytes(4,'little')), patch.object(app.os,'write',side_effect=OSError('failed')), patch.object(app,'command') as command:
            with self.assertRaises(OSError): app.select(IDENT)
            self.assertEqual([c.args[0][1] for c in command.call_args_list], ['-i','+i'])
    def test_readback_mismatch(self):
        @__import__('contextlib').contextmanager
        def opened(*args): yield 42
        with patch.object(app,'read_variable',return_value=RAW), patch.object(app,'open_variable',side_effect=opened), patch.object(app.fcntl,'ioctl',return_value=bytes(4)), patch.object(app.os,'write',return_value=len(RAW[:4]+b'Linux\0')):
            with self.assertRaisesRegex(ValueError,'verification failed'): app.select(IDENT)
    def test_short_write(self):
        @__import__('contextlib').contextmanager
        def opened(*args): yield 42
        with patch.object(app,'read_variable',return_value=RAW), patch.object(app,'open_variable',side_effect=opened), patch.object(app.fcntl,'ioctl',return_value=bytes(4)), patch.object(app.os,'write',return_value=1):
            with self.assertRaisesRegex(OSError,'Short firmware write'): app.select(IDENT)
    def test_unknown_namespace_never_accesses_firmware(self):
        self.data['variable'] = (
            'LimineLastBootedEntry-'
            '11111111-2222-3333-4444-555555555555'
        )
        with (
            patch.object(app, 'read_variable') as read,
            patch.object(app, 'open_variable') as opened,
        ):
            with self.assertRaisesRegex(ValueError, 'unknown namespace'):
                app.select(IDENT)
        read.assert_not_called()
        opened.assert_not_called()

class RestartTests(unittest.TestCase):
    def test_failed_selection_never_restarts(self):
        args=['linksmine','reboot',IDENT]
        with patch.object(app.sys,'argv',args), patch.object(app.os,'geteuid',return_value=1000), patch.object(app,'require_kde'), patch.object(app,'command',side_effect=ValueError('selection failed')), patch.object(app.subprocess,'run') as process:
            with self.assertRaises(ValueError): app.main()
            process.assert_not_called()
    def test_restart_stays_in_user_session(self):
        args=['linksmine','reboot',IDENT]
        with patch.object(app.sys,'argv',args), patch.object(app.os,'geteuid',return_value=1000), patch.object(app,'require_kde'), patch.object(app,'command') as command, patch.object(app.subprocess,'run') as process:
            app.main()
            self.assertEqual(command.call_args.args[0],['/usr/bin/sudo','-n',app.APP,'select',IDENT])
            self.assertEqual(process.call_args.args[0][-1],'logoutAndReboot')

class NamespaceTests(unittest.TestCase):
    CURRENT = (
        'LimineLastBootedEntry-'
        '03884334-1756-4978-9c8c-86fb8998b4ea'
    )

    HISTORICAL = (
        'LimineLastBootedEntry-'
        '513ee0d0-6e43-cb05-b272-f146a2fcb88a'
    )

    UNKNOWN = (
        'LimineLastBootedEntry-'
        '11111111-2222-3333-4444-555555555555'
    )

    def test_current_namespace_recognized(self):
        _, info = app.namespace_info(self.CURRENT)
        self.assertIn('v12.x', info['label'])

    def test_historical_namespace_recognized(self):
        _, info = app.namespace_info(self.HISTORICAL)
        self.assertEqual(info['label'], 'Historical Limine namespace')

    def test_unknown_namespace_not_supported(self):
        with self.assertRaisesRegex(ValueError, 'unknown namespace'):
            app.require_supported_namespace(self.UNKNOWN)

    def test_known_namespaces_supported(self):
        app.require_supported_namespace(self.CURRENT)
        app.require_supported_namespace(self.HISTORICAL)

    def test_description_has_three_lines(self):
        text = app.describe_variable({
            'name': self.CURRENT,
            'current': 'CachyOS/linux-cachyos',
        })

        self.assertEqual(len(text.splitlines()), 3)
        self.assertIn('Currently remembers: CachyOS/linux-cachyos', text)

    def test_historical_description_reports_detected_format(self):
        text = app.describe_variable({
            'name': self.HISTORICAL,
            'current': 'Windows',
        })

        self.assertIn('entry-path value detected', text)

    def test_invalid_variable_name_rejected(self):
        with self.assertRaises(ValueError):
            app.namespace_info('../../etc/passwd')

class SnapshotMenuTests(unittest.TestCase):
    def test_snapshot_subtree_excluded(self):
        text = (
            'remember_last_entry: yes\n'
            '/+CachyOS\n'
            '//linux-cachyos\n'
            'protocol: linux\n'
            '//linux-cachyos-lts\n'
            'protocol: linux\n'
            '//+Snapshots\n'
            '///264 │ 2026-11-15 20:10:11\n'
            '////linux-cachyos\n'
            'protocol: linux\n'
            '////linux-cachyos-lts\n'
            'protocol: linux\n'
            '/Windows\n'
            'protocol: efi\n'
            '/EFI fallback\n'
            'protocol: efi\n'
        )

        paths = [entry['path'] for entry in app.parse_menu(text)]

        self.assertEqual(paths, [
            'CachyOS/linux-cachyos',
            'CachyOS/linux-cachyos-lts',
            'Windows',
            'EFI fallback',
        ])

    def test_snapshot_group_name_variants(self):
        for title in (
                'Snapshots',
                'SNAPSHOTS',
                '.snapshots',
                'Snapshots (generated)',
        ):
            with self.subTest(title=title):
                text = (
                    'remember_last_entry: yes\n'
                    f'/+{title}\n'
                    '//Old Linux\n'
                    'protocol: linux\n'
                    '/Windows\n'
                    'protocol: efi\n'
                )

                paths = [
                    entry['path']
                    for entry in app.parse_menu(text)
                ]

                self.assertEqual(paths, ['Windows'])

    def test_restored_regular_os_remains_available(self):
        text = (
            'remember_last_entry: yes\n'
            '/+CachyOS\n'
            '//linux-cachyos\n'
            'protocol: linux\n'
            'cmdline: rootflags=subvol=/@/.snapshots/6/snapshot\n'
        )

        paths = [entry['path'] for entry in app.parse_menu(text)]

        self.assertEqual(paths, ['CachyOS/linux-cachyos'])

    def test_similar_os_name_not_excluded(self):
        text = (
            'remember_last_entry: yes\n'
            '/+Snapshot Linux\n'
            '//Main kernel\n'
            'protocol: linux\n'
        )

        paths = [entry['path'] for entry in app.parse_menu(text)]

        self.assertEqual(paths, ['Snapshot Linux/Main kernel'])

    def test_only_snapshots_means_no_eligible_entries(self):
        text = (
            'remember_last_entry: yes\n'
            '/+Snapshots\n'
            '//Old Linux\n'
            'protocol: linux\n'
        )

        with self.assertRaisesRegex(
                ValueError,
                'No supported bootable entries',
        ):
            app.parse_menu(text)


if __name__ == '__main__': unittest.main()
