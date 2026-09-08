from pathlib import Path

path=Path(__file__).with_name('v10_update.py')
text=path.read_text(encoding='utf-8')
start=text.index('text = replace_once(\n    text,\n    \'\'\'def loading_html')
end_marker='    "center loading popup html",\n)\n'
end=text.index(end_marker,start)+len(end_marker)
replacement='''old_loading = """def loading_html(message=\\"Loading\\"):\n    d = language_dir()\n    return f\'\'\'<div class=\\"gp-loading-backdrop\\"><div class=\\"gp-loading-card\\" dir=\\"{d}\\">\n      <img src=\\"data:image/png;base64,{_icon_data()}\\" alt=\\"Golden Palace\\">\n      <div class=\\"gp-loading-ring\\"></div><strong>{html.escape(t(message))}</strong>\n    </div></div>\'\'\'\n"""\nnew_loading = """def loading_html(message=\\"Loading\\"):\n    d = language_dir()\n    return f\'\'\'<div class=\\"gp-loading-backdrop\\" role=\\"status\\" aria-live=\\"polite\\"><div class=\\"gp-loading-card\\" dir=\\"{d}\\">\n      <img class=\\"gp-loading-logo\\" src=\\"data:image/jpeg;base64,{_logo_data()}\\" alt=\\"Golden Palace\\">\n      <div class=\\"gp-loading-ring\\"></div><strong>{html.escape(t(message))}</strong>\n    </div></div>\'\'\'\n"""\ntext = replace_once(text, old_loading, new_loading, "center loading popup html")\n'''
path.write_text(text[:start]+replacement+text[end:],encoding='utf-8')
print('v10 updater repaired')
