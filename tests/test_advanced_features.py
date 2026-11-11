import json
from pathlib import Path

from agent_code.advanced_features import CheckpointStore, analyze_project, render_project_summary, run_validation


def test_project_analysis_skips_secrets_and_build_dirs(tmp_path):
    (tmp_path / 'main.py').write_text('print(1)', encoding='utf-8')
    (tmp_path / 'pyproject.toml').write_text('[project]', encoding='utf-8')
    (tmp_path / '.env').write_text('TOKEN=secret', encoding='utf-8')
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules' / 'bad.js').write_text('secret', encoding='utf-8')
    info = analyze_project(tmp_path)
    assert 'Python' in info['languages']
    assert 'pyproject.toml' in info['configs']
    assert '.env' not in info['files']
    assert not any('node_modules' in f for f in info['files'])
    assert 'Project root:' in render_project_summary(info)


def test_checkpoint_restores_modified_and_removes_new_agent_file(tmp_path):
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    (workspace / 'old.txt').write_text('before', encoding='utf-8')
    store = CheckpointStore(workspace, tmp_path / 'checkpoints')
    cp = store.create('unit test')
    store.capture_before(cp['id'], 'old.txt')
    store.capture_before(cp['id'], 'new.txt')
    (workspace / 'old.txt').write_text('after', encoding='utf-8')
    (workspace / 'new.txt').write_text('new', encoding='utf-8')
    store.finalize(cp['id'])
    result = store.restore(cp['id'], force=True)
    assert (workspace / 'old.txt').read_text(encoding='utf-8') == 'before'
    assert not (workspace / 'new.txt').exists()
    assert result['restored'] == ['old.txt']
    assert result['removed_created_files'] == ['new.txt']


def test_checkpoint_detects_post_task_conflicts(tmp_path):
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    (workspace / 'x.txt').write_text('before', encoding='utf-8')
    store = CheckpointStore(workspace, tmp_path / 'checkpoints')
    cp = store.create('conflict')
    store.capture_before(cp['id'], 'x.txt')
    (workspace / 'x.txt').write_text('agent result', encoding='utf-8')
    store.finalize(cp['id'])
    (workspace / 'x.txt').write_text('user edit after task', encoding='utf-8')
    result = store.restore(cp['id'], force=False)
    assert result['conflicts'] == ['x.txt']
    assert (workspace / 'x.txt').read_text(encoding='utf-8') == 'user edit after task'


def test_validation_returns_actual_exit_code(tmp_path):
    result = run_validation(['python', '-c', 'print("ok")'], tmp_path)
    assert result['status'] == 'passed'
    assert result['returncode'] == 0
    assert 'ok' in result['stdout']


def test_validation_reports_missing_command(tmp_path):
    result = run_validation(['agent-code-command-definitely-missing'], tmp_path)
    assert result['status'] == 'missing_dependency'


def test_task_report_lists_only_real_changes(tmp_path):
    from agent_code.advanced_features import build_task_report, format_task_report
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    (workspace / 'changed.py').write_text('before', encoding='utf-8')
    store = CheckpointStore(workspace, tmp_path / 'checkpoints')
    cp = store.create('report test')
    store.capture_before(cp['id'], 'changed.py')
    store.capture_before(cp['id'], 'new.py')
    store.capture_before(cp['id'], 'unchanged.py')
    (workspace / 'changed.py').write_text('after', encoding='utf-8')
    (workspace / 'new.py').write_text('new', encoding='utf-8')
    (workspace / 'unchanged.py').write_text('same', encoding='utf-8')
    # unchanged.py was absent at checkpoint time, so its creation is a real change.
    final = store.finalize(cp['id'])
    report = build_task_report(final, 'completed', {'status': 'passed'})
    assert report['changed_count'] == 3
    assert set(report['changed_files']) == {'changed.py', 'new.py', 'unchanged.py'}
    text = format_task_report(report)
    assert 'Task Completed' in text
    assert 'Validation passed' in text
    assert cp['id'] in text


def test_task_report_does_not_claim_unrun_validation():
    from agent_code.advanced_features import build_task_report, format_task_report
    report = build_task_report(None, 'stopped')
    assert 'Validation not run' in format_task_report(report)
    assert report['changed_count'] == 0


def test_task_report_includes_truthful_line_change_counts(tmp_path):
    from agent_code.advanced_features import CheckpointStore, build_task_report
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    (workspace / 'sample.py').write_text('one\ntwo\n', encoding='utf-8')
    store = CheckpointStore(workspace, tmp_path / 'checkpoints')
    cp = store.create('diff stats')
    store.capture_before(cp['id'], 'sample.py')
    (workspace / 'sample.py').write_text('one\nthree\nfour\n', encoding='utf-8')
    final = store.finalize(cp['id'])
    report = build_task_report(final)
    assert report['changed_files'] == ['sample.py']
    assert report['additions'] == 2
    assert report['deletions'] == 1
    assert report['diff_stats']['sample.py']['kind'] == 'text'


def test_task_report_marks_binary_changes_without_fake_line_counts(tmp_path):
    from agent_code.advanced_features import CheckpointStore, build_task_report
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    (workspace / 'asset.bin').write_bytes(b'old\x00data')
    store = CheckpointStore(workspace, tmp_path / 'checkpoints')
    cp = store.create('binary diff')
    store.capture_before(cp['id'], 'asset.bin')
    (workspace / 'asset.bin').write_bytes(b'new\x00data')
    report = build_task_report(store.finalize(cp['id']))
    assert report['changed_files'] == ['asset.bin']
    assert report['diff_stats']['asset.bin']['kind'] == 'binary'
    assert report['additions'] == report['deletions'] == 0


def test_checkpoint_unified_diff_shows_real_text_changes(tmp_path):
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    target = workspace / 'app.py'
    target.write_text('alpha\nbeta\n', encoding='utf-8')
    store = CheckpointStore(workspace, tmp_path / 'checkpoints')
    cp = store.create('visual diff')
    store.capture_before(cp['id'], 'app.py')
    target.write_text('alpha\ngamma\ndelta\n', encoding='utf-8')
    store.finalize(cp['id'])
    diff = store.unified_diff(cp['id'], 'app.py')
    assert '--- before/app.py' in diff
    assert '+++ after/app.py' in diff
    assert '-beta' in diff
    assert '+gamma' in diff and '+delta' in diff


def test_checkpoint_unified_diff_rejects_uncaptured_path(tmp_path):
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    (workspace / 'secret.txt').write_text('do not expose', encoding='utf-8')
    store = CheckpointStore(workspace, tmp_path / 'checkpoints')
    cp = store.create('scope')
    try:
        store.unified_diff(cp['id'], 'secret.txt')
    except ValueError as exc:
        assert 'not part' in str(exc)
    else:
        raise AssertionError('uncaptured paths must not be diffed')


def test_checkpoint_unified_diff_marks_binary_files(tmp_path):
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    target = workspace / 'asset.bin'
    target.write_bytes(b'old\x00bytes')
    store = CheckpointStore(workspace, tmp_path / 'checkpoints')
    cp = store.create('binary')
    store.capture_before(cp['id'], 'asset.bin')
    target.write_bytes(b'new\x00bytes')
    assert 'Binary file changed' in store.unified_diff(cp['id'], 'asset.bin')


def test_restore_preview_is_read_only_and_supports_selected_files(tmp_path):
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    (workspace / 'a.txt').write_text('before-a', encoding='utf-8')
    (workspace / 'b.txt').write_text('before-b', encoding='utf-8')
    store = CheckpointStore(workspace, tmp_path / 'checkpoints')
    cp = store.create('selective restore')
    store.capture_before(cp['id'], 'a.txt')
    store.capture_before(cp['id'], 'b.txt')
    (workspace / 'a.txt').write_text('after-a', encoding='utf-8')
    (workspace / 'b.txt').write_text('after-b', encoding='utf-8')
    store.finalize(cp['id'])

    preview = store.preview_restore(cp['id'], ['a.txt'])
    assert preview['restore_count'] == 1
    assert preview['actions'] == [{'path': 'a.txt', 'action': 'restore'}]
    assert (workspace / 'a.txt').read_text(encoding='utf-8') == 'after-a'

    result = store.restore(cp['id'], selected_paths=['a.txt'])
    assert result['restored'] == ['a.txt']
    assert (workspace / 'a.txt').read_text(encoding='utf-8') == 'before-a'
    assert (workspace / 'b.txt').read_text(encoding='utf-8') == 'after-b'


def test_restore_rejects_paths_outside_checkpoint(tmp_path):
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    store = CheckpointStore(workspace, tmp_path / 'checkpoints')
    cp = store.create('scope')
    for operation in (lambda: store.preview_restore(cp['id'], ['outside.txt']),
                      lambda: store.restore(cp['id'], selected_paths=['outside.txt'])):
        try:
            operation()
        except ValueError as exc:
            assert 'not part' in str(exc)
        else:
            raise AssertionError('out-of-checkpoint paths must be rejected')


def test_project_analysis_honors_agentignore_and_gitignore(tmp_path):
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src' / 'keep.py').write_text('print(1)', encoding='utf-8')
    (tmp_path / 'src' / 'generated.py').write_text('generated', encoding='utf-8')
    (tmp_path / 'artifacts').mkdir()
    (tmp_path / 'artifacts' / 'bundle.js').write_text('bundle', encoding='utf-8')
    (tmp_path / 'notes.tmp').write_text('temporary', encoding='utf-8')
    (tmp_path / '.gitignore').write_text('*.tmp\n', encoding='utf-8')
    (tmp_path / '.agentignore').write_text('src/generated.py\nartifacts/\n', encoding='utf-8')

    info = analyze_project(tmp_path)
    assert 'src/keep.py' in info['files']
    assert 'src/generated.py' not in info['files']
    assert 'artifacts/bundle.js' not in info['files']
    assert 'notes.tmp' not in info['files']
    assert info['ignore_rules'] == 3
    assert set(info['ignore_files']) == {'.gitignore', '.agentignore'}


def test_project_ignore_rules_cannot_expose_sensitive_files(tmp_path):
    (tmp_path / '.env').write_text('API_KEY=secret', encoding='utf-8')
    (tmp_path / 'credentials.txt').write_text('secret', encoding='utf-8')
    (tmp_path / '.agentignore').write_text('!*.env\n!credentials.txt\n', encoding='utf-8')
    info = analyze_project(tmp_path)
    assert '.env' not in info['files']
    assert 'credentials.txt' not in info['files']


def test_project_analysis_supports_negated_file_inside_ignored_directory(tmp_path):
    (tmp_path / 'cache').mkdir()
    (tmp_path / 'cache' / 'keep.py').write_text('important', encoding='utf-8')
    (tmp_path / 'cache' / 'drop.py').write_text('generated', encoding='utf-8')
    (tmp_path / '.agentignore').write_text('cache/\n!cache/keep.py\n', encoding='utf-8')
    info = analyze_project(tmp_path)
    assert 'cache/keep.py' in info['files']
    assert 'cache/drop.py' not in info['files']


def test_detect_validation_command_for_python_rust_and_go(tmp_path):
    from agent_code.advanced_features import detect_validation_command
    (tmp_path / 'pyproject.toml').write_text('[project]', encoding='utf-8')
    assert detect_validation_command(tmp_path) == 'python -m pytest -q'
    (tmp_path / 'pyproject.toml').unlink()
    (tmp_path / 'Cargo.toml').write_text('[package]', encoding='utf-8')
    assert detect_validation_command(tmp_path) == 'cargo test'
    (tmp_path / 'Cargo.toml').unlink()
    (tmp_path / 'go.mod').write_text('module example', encoding='utf-8')
    assert detect_validation_command(tmp_path) == 'go test ./...'


def test_detect_validation_command_selects_node_package_manager(tmp_path):
    import json
    from agent_code.advanced_features import detect_validation_command
    (tmp_path / 'package.json').write_text(json.dumps({'scripts': {'test': 'vitest run'}}), encoding='utf-8')
    assert detect_validation_command(tmp_path) == 'npm test'
    (tmp_path / 'pnpm-lock.yaml').write_text('lockfileVersion: 9', encoding='utf-8')
    assert detect_validation_command(tmp_path) == 'pnpm test'
    (tmp_path / 'pnpm-lock.yaml').unlink()
    (tmp_path / 'yarn.lock').write_text('# yarn', encoding='utf-8')
    assert detect_validation_command(tmp_path) == 'yarn test'


def test_detect_validation_command_does_not_run_or_guess_missing_node_test(tmp_path):
    import json
    from agent_code.advanced_features import detect_validation_command
    (tmp_path / 'package.json').write_text(json.dumps({'scripts': {'build': 'vite build'}}), encoding='utf-8')
    assert detect_validation_command(tmp_path) is None
