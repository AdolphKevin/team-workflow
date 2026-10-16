"""Published design links point at the source commit or become readable paths."""
import copy
import subprocess
import unittest
from unittest.mock import patch

import test_coordination as shared
import test_platform as platform_tests
import test_project_platform as github_tests
import test_workflow as fixtures
from common import Invalid, read, write
import coordination
import design_files
import plan_fixtures as plans
from platform_fixtures import transport
from tw_runtime.team import platform_script
from tw_runtime.project import platform_problems


class DesignLinks(unittest.TestCase):
    base = shared.CoordinationCases
    setUp, git, check, prepare, github, publish_fixture, body = (
        base.setUp, base.git, base.check, base.prepare, base.github, base.publish_fixture, base.body)

    def publication(self):
        self.prepare()
        self.design['sections'][1]['body'] = '\n'.join([
            '[Guide](../guide.md#install) and ![Diagram](images/flow.png)',
            '[../guide.md](../guide.md) and [Outside](../../../outside.md)',
            '[Absolute](https://example.invalid/guide) [Anchor](#here) [Root](/root.md)',
            '`[Code](../code.md)` and ``![Code](../code.png)``',
            '```markdown', '[Fence](../fence.md)', '```',
            '~~~md', '![Fence](../fence.png)', '~~~',
            '[Nested](../guide_(v2).md "Guide title")',
        ])
        original = plans.design_source(self.root, self.design)
        source = original.parent / 'docs/plans/design.md'
        plans.write_design(source, self.design)
        subprocess.run(['git', '-C', str(original.parent), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(original.parent), 'commit', '-qm', 'Nested design fixture'], check=True, capture_output=True)
        return source

    def test_declared_file_url_rewrites_links_and_images_but_preserves_code(self):
        source = self.publication()
        self.profile['platform']['operations'].append('file-url')
        fixtures.write_config(self.root, self.profile)
        calls = []

        def call(root, operation, *args):
            self.assertEqual(operation, 'file-url')
            calls.append(args)
            return {'url': 'https://code.invalid/files/' + args[3] + '/' + args[5]}

        with patch.object(platform_script, 'call', side_effect=call):
            reference, text = design_files.publication(self.root, source, self.design)
        prefix = 'https://code.invalid/files/' + reference['commit'] + '/'
        self.assertIn('[Guide](' + prefix + 'docs/guide.md#install)', text)
        self.assertIn('![Diagram](' + prefix + 'docs/plans/images/flow.png)', text)
        self.assertIn('[Nested](' + prefix + 'docs/guide_(v2).md "Guide title")', text)
        self.assertIn('Outside（`../outside.md`）', text)
        self.assertEqual(len(calls), 4)
        self.assertIn('`[Code](../code.md)` and ``![Code](../code.png)``', text)
        self.assertIn('```markdown\n[Fence](../fence.md)\n```', text)
        self.assertIn('~~~md\n![Fence](../fence.png)\n~~~', text)
        self.assertIn('[Absolute](https://example.invalid/guide) [Anchor](#here) [Root](/root.md)', text)

    def test_without_file_url_relative_targets_become_plain_paths(self):
        source = self.publication()
        with patch.object(platform_script, 'call', side_effect=AssertionError('No undeclared operation')):
            _, text = design_files.publication(self.root, source, self.design)
        self.assertIn('Guide（`docs/guide.md#install`）', text)
        self.assertIn('Diagram（`docs/plans/images/flow.png`）', text)
        self.assertIn('`docs/guide.md` and Outside（`../outside.md`）', text)
        self.assertNotIn('[Guide](../guide.md#install)', text)

    def test_reference_style_links_and_images_resolve_without_rewriting_code(self):
        import design_links
        source = '[Guide][g] ![Picture][p] [g][] [g]\n\n[g]: ../guide.md#intro "Title"\n[p]: img.png\n' \
                 + '`[g]: code.md`\n```md\n[p]: fence.png\n```\n'
        reference = {'path': 'docs/plans/design.md'}
        urls = design_links.rewrite(source, reference, lambda path: 'https://code.invalid/' + path)
        self.assertIn('[g]: https://code.invalid/docs/guide.md#intro "Title"', urls)
        self.assertIn('[p]: https://code.invalid/docs/plans/img.png', urls)
        plain = design_links.rewrite(source, reference)
        self.assertIn('Guide（`docs/guide.md#intro`） Picture（`docs/plans/img.png`）', plain)
        self.assertIn('`[g]: code.md`\n```md\n[p]: fence.png\n```', plain)

    def test_description_warning_uses_the_rewritten_display(self):
        source = self.publication()
        with patch.object(platform_script, 'call', side_effect=transport(self.github)):
            draft = coordination.draft_design(self.url, self.design, path=source, root=self.root)
            self.publish_fixture(draft, 'alice')
            self.issue['comments_data'].append({'html_url': 'https://github.com/example/project/pull/3',
                'body': draft['pr_description'], 'kind': 'change', 'user': {'login': 'alice'}})
            # Preserve the normalized change kind instead of the API fixture's comment default.
            original = platform_script.task
            def task(root, identity):
                value = original(root, identity)
                value['items'][-1]['kind'] = 'change'
                return value
            with patch.object(platform_script, 'task', side_effect=task):
                self.assertEqual(coordination.load(self.url, root=self.root)['warnings'], [])


class FileURLContract(unittest.TestCase):
    setUp, response = platform_tests.PlatformContract.setUp, platform_tests.PlatformContract.response

    def test_file_url_is_optional_validated_and_cached_per_invocation(self):
        self.config['platform']['operations'].append('file-url')
        write(self.root / '.tw/config.json', self.config)
        self.assertEqual(platform_problems(self.config['platform']), [])
        revision = 'a' * 40
        url = 'https://code.example/group/repo/blob/' + revision + '/docs/design.md#intro'
        self.response('file-url', {'url': url})
        arguments = ('--repo', 'code.example/group/repo', '--revision', revision, '--path', 'docs/design.md#intro')
        self.assertEqual(platform_script.call(self.root, 'file-url', *arguments), {'url': url})
        self.assertEqual(platform_script.call(self.root, 'file-url', *arguments), {'url': url})
        self.assertEqual(len(self.log.read_text().splitlines()), 1)
        platform_script.clear_cache()
        self.assertEqual(platform_script.call(self.root, 'file-url', *arguments), {'url': url})
        self.assertEqual(len(self.log.read_text().splitlines()), 2)
        for invalid in ['docs/design.md', '//host/path', 'file:///tmp/file', '', 7]:
            with self.subTest(url=invalid), self.assertRaises(Invalid):
                platform_script.validate('file-url', {'url': invalid}, arguments)


class DesignLinkPaths(unittest.TestCase):
    def test_encoded_absolute_target_is_outside_repository(self):
        import design_links
        calls = []
        def url(path):
            calls.append(path)
            return 'https://code.invalid/' + path
        self.assertEqual(design_links.rewrite('[Outside](%2Foutside.md)', {'path': 'docs/design.md'}, url),
                         'Outside（`/outside.md`）')
        self.assertEqual(calls, [])

    def test_reference_label_equal_to_target_is_just_the_path(self):
        import design_links
        self.assertEqual(design_links.rewrite('[../guide.md][g]\n\n[g]: ../guide.md\n',
                                             {'path': 'docs/plans/design.md'}), '`docs/guide.md`\n\n')


class GitHubFileURL(unittest.TestCase):
    base = github_tests.ProjectPlatform
    setUp, route, save, call = base.setUp, base.route, base.save, base.call

    def test_github_file_url_needs_no_api_and_preserves_fragment(self):
        config = read(self.root / '.tw/config.json')
        config['platform']['operations'].append('file-url')
        write(self.root / '.tw/config.json', config)
        result = self.call('file-url', '--repo', 'github.com/example/project', '--revision', 'a' * 40,
                           '--path', 'docs/a file.md#section')
        self.assertEqual(result, {'url': 'https://github.com/example/project/blob/' + 'a' * 40 + '/docs/a%20file.md#section'})
        self.assertFalse(self.log.exists())
