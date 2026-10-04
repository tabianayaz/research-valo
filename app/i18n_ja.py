"""Japanese UI strings keyed by the English source text.

Display only: none of these strings are written to the database or exports.
Placeholders in braces (``{name}``) must be kept unchanged. Wording follows the
project's conservative style (no "best", "optimal" or "improved" claims).
"""

from __future__ import annotations

JA: dict[str, str] = {
    # ------------------------------------------------------------ navigation
    "HCI research prototype": "HCI研究用プロトタイプ",
    "Home": "ホーム",
    "Setup": "参加者設定",
    "Crosshair": "クロスヘア",
    "Assessment": "測定",
    "Results": "結果",
    "Recommendation": "推薦",
    "Comparison": "比較",
    "History": "履歴",
    "Settings": "設定",
    "Participant: {player_id}": "参加者: {player_id}",
    "No participant selected": "参加者が選択されていません",
    "Database: {name}": "データベース: {name}",

    # ------------------------------------------------------------ common Qt
    "OK": "OK",
    "&OK": "OK(&O)",
    "Cancel": "キャンセル",
    "&Cancel": "キャンセル(&C)",
    "Close": "閉じる",
    "&Close": "閉じる(&C)",
    "Yes": "はい",
    "&Yes": "はい(&Y)",
    "No": "いいえ",
    "&No": "いいえ(&N)",

    # ------------------------------------------------------------ canonical codes (display only)
    "flick": "フリックエイム",
    "tracking": "トラッキング",
    "switching": "ターゲットスイッチング",
    "baseline": "ベースライン",
    "candidate": "候補",
    "custom": "カスタム",
    "in_progress": "進行中",
    "completed": "完了",
    "aborted": "中断",
    "standard": "標準",
    "practice": "練習",
    "familiarization": "慣熟",
    "experimental": "本測定",
    "combined": "練習＋本測定",
    "counterbalanced": "カウンターバランス",
    "debug_fixed": "デバッグ（固定順）",
    "individual": "個別",
    "hit": "ヒット",
    "miss": "ミス",
    "timeout": "タイムアウト",
    "tracked": "追従",
    "incomplete": "未完了",
    "valid": "有効",
    "exact": "完全一致",
    "approximate": "近似",
    "not representable": "表現不可",
    "not_representable": "表現不可",
    "unknown": "不明",
    "imported": "取り込み済み",
    "source_only": "出典のみ保存",
    "duplicate": "重複",
    "invalid": "無効",

    # ------------------------------------------------------------ tasks
    "Flick Aim": "フリックエイム",
    "Tracking": "トラッキング",
    "Target Switching": "ターゲットスイッチング",
    "A single target appears. Move the crosshair onto it and click as quickly and accurately as possible.":
        "ターゲットが1つ表示されます。クロスヘアをターゲットに合わせ、できるだけ速く正確にクリックしてください。",
    "A target moves along a reproducible path. Keep the crosshair on the target for the duration of the trial.":
        "ターゲットが再現可能な軌道で動きます。試行の間、クロスヘアをターゲットに合わせ続けてください。",
    "Several targets are shown. Click the highlighted one; the next target is highlighted immediately.":
        "複数のターゲットが表示されます。強調表示されたターゲットをクリックすると、すぐに次のターゲットが強調表示されます。",
    "latest completed baseline session of the same task": "同じ課題の最新の完了済みベースラインセッション",

    # ------------------------------------------------------------ home
    "Start Assessment": "測定を開始",
    "Begin with player setup (Ctrl+2)": "参加者設定から始めます (Ctrl+2)",
    "Crosshair Database": "クロスヘアデータベース",
    "Previous Results": "過去の結果",
    "Research workflow": "研究の流れ",
    "Database": "データベース",
    "Players": "参加者",
    "Sessions": "セッション",
    "Trials": "試行",
    "Crosshairs": "クロスヘア",
    "Recommendations": "推薦",
    "Measure": "測定",
    "Aim assessment with the standard crosshair": "標準クロスヘアでエイムを測定",
    "Analyze": "分析",
    "Build a profile of measured aiming characteristics": "測定されたエイム特性のプロファイルを作成",
    "Recommend": "推薦",
    "Present several crosshair candidates": "複数のクロスヘア候補を提示",
    "Try": "試用",
    "Apply a candidate of your choice": "選んだ候補を適用",
    "Re-measure": "再測定",
    "Repeat the relevant assessment": "該当する測定を再度実施",
    "Compare": "比較",
    "Review the measured differences": "測定された差を確認",
    "This research prototype measures your aiming performance, analyzes your measured characteristics, "
    "and presents crosshair candidates that may be suitable for further testing. It does not claim that "
    "any crosshair is universally best; it helps you find settings worth trying, then compares measured "
    "results.":
        "この研究用プロトタイプは、エイム操作を測定して測定された特性を分析し、さらに試す価値があるかもしれない"
        "クロスヘア候補を提示します。どのクロスヘアが誰にとっても最良であるとは主張しません。試す価値のある設定を"
        "見つける手助けをし、その後に測定結果を比較します。",

    # ------------------------------------------------------------ setup
    "Player Setup": "参加者設定",
    "Anonymous participant information. Do not enter your real name, email or any other personally "
    "identifying information.":
        "匿名の参加者情報です。氏名、メールアドレスなど個人を特定できる情報は入力しないでください。",
    "Participant": "参加者",
    "e.g. P-3F9A": "例: P-3F9A",
    "Generate ID": "IDを生成",
    "Player ID": "参加者ID",
    "FPS experience": "FPS経験",
    "Aim training frequency": "エイム練習の頻度",
    "Not specified": "未回答",
    "Less than 6 months": "6か月未満",
    "6 months - 1 year": "6か月〜1年",
    "1 - 3 years": "1〜3年",
    "More than 3 years": "3年以上",
    "Never": "まったくしない",
    "Rarely (less than once a month)": "まれに（月1回未満）",
    "Sometimes (a few times a month)": "ときどき（月に数回）",
    "Regularly (weekly)": "定期的に（毎週）",
    "Daily": "毎日",
    "Mouse and display": "マウスとディスプレイ",
    "Mouse DPI": "マウスDPI",
    "In-game sensitivity": "ゲーム内感度",
    "eDPI (DPI × sensitivity)": "eDPI（DPI × 感度）",
    "Detect": "検出",
    "Use the resolution of the screen this window is on": "このウィンドウがある画面の解像度を使用します",
    "Display resolution": "画面解像度",
    "eDPI is computed as DPI × in-game sensitivity. Sensitivity scales differ between games, so record "
    "the game the sensitivity refers to in a later milestone if cross-game comparison becomes necessary.":
        "eDPI は DPI × ゲーム内感度で計算されます。感度のスケールはゲームごとに異なるため、ゲーム間の比較が"
        "必要になった場合は、後のマイルストーンで感度がどのゲームのものかを記録してください。",
    "Save and Continue": "保存して次へ",
    "Loaded existing participant {player_id}. Saving will update the profile; past sessions keep their "
    "own recorded settings.":
        "既存の参加者 {player_id} を読み込みました。保存するとプロファイルが更新されます。過去のセッションには"
        "記録時の設定がそのまま残ります。",
    "Could not save participant: {error}": "参加者を保存できませんでした: {error}",
    "Participant {player_id} saved.": "参加者 {player_id} を保存しました。",
    "Player ID must be 2-32 characters using only letters, digits, '_' or '-'.":
        "参加者IDは英字・数字・「_」・「-」のみを使い、2〜32文字で入力してください。",

    # ------------------------------------------------------------ crosshair page
    "Standard crosshair, crosshair settings and the candidate crosshair database.":
        "標準クロスヘア、クロスヘア設定、候補クロスヘアのデータベースです。",
    "Standard crosshair": "標準クロスヘア",
    "Crosshair settings": "クロスヘア設定",
    "Crosshair database": "クロスヘアデータベース",
    "Experimental baseline": "実験のベースライン",
    "Every participant performs the initial assessment with this fixed crosshair. Holding it constant "
    "makes first measurements comparable between participants and gives each participant a reference "
    "for later candidate comparisons.":
        "すべての参加者は、この固定クロスヘアで最初の測定を行います。これを一定に保つことで、参加者間で最初の"
        "測定値を比較でき、各参加者にとって後の候補比較の基準になります。",
    "Preview": "プレビュー",
    "Research decision required: the standard crosshair values are placeholders and have not been "
    "confirmed. Set them and \"baseline_confirmed\": true in {file} before collecting data.":
        "研究上の判断が必要です: 標準クロスヘアの値は仮の値で、まだ確定していません。データ収集の前に、"
        "{file} で値を設定し \"baseline_confirmed\": true にしてください。",
    "Crosshair ID {crosshair_id} · defined in {path} · background {background}":
        "クロスヘアID {crosshair_id} · 定義ファイル {path} · 背景色 {background}",
    "Actual size (1 unit = {px} physical px)": "実寸（1単位 = 物理ピクセル {px} 個）",
    "Magnified ×{zoom} (inspection only)": "×{zoom} 拡大（確認用）",
    "Color": "色",
    "Size (arm length)": "サイズ（線の長さ）",
    "Thickness": "太さ",
    "Gap (center to arm)": "ギャップ（中心から線まで）",
    "Outline": "アウトライン",
    "Outline thickness": "アウトラインの太さ",
    "Opacity": "不透明度",
    "On": "オン",
    "Off": "オフ",
    "Size": "サイズ",
    "Gap": "ギャップ",

    # ------------------------------------------------------------ crosshair editor
    "Choose colour": "色を選択",
    "Enabled": "有効",
    "Load": "読み込み",
    "Reset to standard": "標準に戻す",
    "Load an existing crosshair": "既存のクロスヘアを読み込む",
    "Name for this custom crosshair": "このカスタムクロスヘアの名前",
    "Save as custom crosshair": "カスタムクロスヘアとして保存",
    "The outline is drawn black at the same opacity as the lines. Rendering uses exact physical pixels; "
    "see docs for the geometry rules.":
        "アウトラインは線と同じ不透明度の黒で描画されます。描画は物理ピクセル単位で行われます。形状の規則は"
        "ドキュメントを参照してください。",
    "Crosshair colour": "クロスヘアの色",
    "Enter a name before saving.": "保存する前に名前を入力してください。",
    "Could not save: {error}": "保存できませんでした: {error}",
    "Saved custom crosshair '{name}'.": "カスタムクロスヘア「{name}」を保存しました。",
    "Delete": "削除",
    "Delete the selected custom crosshair. Crosshairs used by recorded sessions or recommendations are kept.":
        "選択したカスタムクロスヘアを削除します。記録済みのセッションや推薦で使用されたクロスヘアは保持されます。",
    "Delete custom crosshair": "カスタムクロスヘアの削除",
    "Delete the custom crosshair '{name}'? This cannot be undone.":
        "カスタムクロスヘア「{name}」を削除しますか？この操作は元に戻せません。",
    "'{name}' is used by recorded sessions or recommendations and is kept.":
        "「{name}」は記録済みのセッションまたは推薦で使用されているため保持されます。",
    "Could not delete: {error}": "削除できませんでした: {error}",
    "Deleted custom crosshair '{name}'.": "カスタムクロスヘア「{name}」を削除しました。",
    "Only custom crosshairs can be deleted.": "削除できるのはカスタムクロスヘアのみです。",
    "This crosshair is used by recorded sessions or recommendations and is kept.":
        "このクロスヘアは記録済みのセッションまたは推薦で使用されているため保持されます。",
    "color must be a hex colour like #RRGGBB.": "色は #RRGGBB 形式の16進数で指定してください。",

    # ------------------------------------------------------------ crosshair database
    "Original": "元の表示",
    "Research model": "研究モデル",
    "Fidelity": "再現度",
    "Source": "出典",
    "Player": "選手",
    "Share code": "共有コード",
    "All": "すべて",
    "Exact": "完全一致",
    "Approximate": "近似",
    "Not representable": "表現不可",
    "Parse: {text}": "解析: {text}",
    "Resolve: {text}": "解決: {text}",
    "Difference: {text}": "差異: {text}",
    "Info: {text}": "情報: {text}",
    "Import VALORANT crosshair codes": "VALORANT クロスヘアコードの取り込み",
    "Provenance is stored with every code. Only enter publicly available player names. The importer "
    "stores candidate data; it does not make recommendations.":
        "各コードには出典情報が保存されます。公開されている選手名のみを入力してください。取り込み機能は候補"
        "データを保存するだけで、推薦は行いません。",
    "Optional, e.g. the page the codes came from": "任意。例: コードの取得元ページ",
    "Optional, applies to every code below": "任意。以下のすべてのコードに適用されます",
    "Source name": "出典名",
    "Source URL": "出典URL",
    "Player (public)": "選手（公開情報）",
    "One entry per line: CODE  or  PLAYER, CODE  or  PLAYER, CODE, URL (comma or tab separated). "
    "Per-line player/URL override the fields above.":
        "1行に1件: コード、または 選手, コード、または 選手, コード, URL（カンマまたはタブ区切り）。"
        "行ごとの選手名/URLは上の欄より優先されます。",
    "Load from text file…": "テキストファイルから読み込む…",
    "Import": "取り込む",
    "Open codes": "コードを開く",
    "Text files (*.txt);;All files (*)": "テキストファイル (*.txt);;すべてのファイル (*)",
    "Source name is required.": "出典名は必須です。",
    "Import failed: {error}": "取り込みに失敗しました: {error}",
    "Imported {imported} as candidates, {source_only} stored as source only (not representable), "
    "{duplicates} duplicates skipped, {invalid} invalid.":
        "候補として {imported} 件を取り込み、{source_only} 件を出典のみ保存（表現不可）、"
        "重複 {duplicates} 件をスキップ、無効 {invalid} 件。",
    "line {number}": "{number} 行目",
    "Publicly collected or manually provided crosshair configurations. This source data is stored "
    "separately from measurement data. 'Original' renders the static VALORANT crosshair; 'Research model' "
    "renders what the experiment would use.":
        "公開情報から収集した、または手動で提供されたクロスヘア設定です。この出典データは測定データとは別に"
        "保存されます。「元の表示」は静的な VALORANT のクロスヘア、「研究モデル」は実験で使われる形を表示します。",
    "Import VALORANT codes…": "VALORANT コードを取り込む…",
    "Update from Liquipedia…": "Liquipedia から更新…",
    "Manual update through the Liquipedia API (never automatic)":
        "Liquipedia API を使った手動更新（自動では実行されません）",
    "Open in editor": "エディタで開く",
    "No crosshair sources yet. Use 'Import VALORANT codes…' to add candidates.":
        "クロスヘアの出典はまだありません。「VALORANT コードを取り込む…」で候補を追加してください。",
    "Details": "詳細",
    "Select a row to see mapping differences and warnings.": "行を選択すると、変換時の差異と警告を表示します。",
    "{shown} shown · {usable} usable as candidates · {total} sources total":
        "{shown} 件表示 · 候補として使用可能 {usable} 件 · 出典合計 {total} 件",
    "Not representable in the research model": "研究モデルでは表現できません",
    "Source: {name}": "出典: {name}",
    "Retrieved: {when}": "取得日時: {when}",
    " · published date: {date}": " · 公開日: {date}",
    "License: {license} · Attribution: {attribution}": "ライセンス: {license} · 帰属表示: {attribution}",
    "Code: {code}": "コード: {code}",
    "Fidelity: {fidelity}": "再現度: {fidelity}",
    "on {value}": "オン {value}",
    "off": "オフ",
    "Research model: color {color}, size {size}, thickness {thickness}, gap {gap}, outline {outline}, "
    "opacity {opacity}":
        "研究モデル: 色 {color}、サイズ {size}、太さ {thickness}、ギャップ {gap}、アウトライン {outline}、"
        "不透明度 {opacity}",
    "No differences or warnings.": "差異や警告はありません。",

    # ------------------------------------------------------------ Liquipedia dialog
    "Update crosshair database from Liquipedia": "Liquipedia からクロスヘアデータベースを更新",
    "Reads VALORANT crosshair share codes from Liquipedia player pages through the official MediaWiki "
    "API, following Liquipedia's API terms: at most one request every {interval} s, an identifying "
    "User-Agent with your contact, and cached responses (re-used for {days} days). Content is licensed "
    "{license}; every record keeps a permalink for attribution. Existing records are never overwritten; "
    "duplicates are skipped.":
        "Liquipedia の選手ページから、公式 MediaWiki API を通じて VALORANT のクロスヘア共有コードを読み取ります。"
        "Liquipedia の API 規約に従い、リクエストは最大 {interval} 秒に1回、連絡先を含む User-Agent を送信し、"
        "応答はキャッシュされます（{days} 日間再利用）。コンテンツのライセンスは {license} で、各レコードには"
        "帰属表示用のパーマリンクが保存されます。既存のレコードは上書きされず、重複はスキップされます。",
    "e-mail or project URL (sent in the User-Agent)": "メールアドレスまたはプロジェクトURL（User-Agent に含めて送信）",
    "Contact": "連絡先",
    "Ignore cache and re-download": "キャッシュを無視して再取得",
    "Start update": "更新を開始",
    "Updating… (this takes a few seconds per request)": "更新中…（1リクエストにつき数秒かかります）",
    "Skipped pages:": "スキップしたページ:",
    "{imported} new candidates, {source_only} stored as source only, {duplicates} already stored, "
    "{invalid} invalid codes, {skipped} pages skipped.":
        "新しい候補 {imported} 件、出典のみ保存 {source_only} 件、保存済み {duplicates} 件、"
        "無効なコード {invalid} 件、スキップしたページ {skipped} 件。",
    "Update stopped: {message} Nothing was imported.": "更新を中止しました: {message} 何も取り込まれていません。",

    # ------------------------------------------------------------ assessment page
    "Aim Assessment": "エイム測定",
    "Choose an assessment task. During a task the screen shows only the target, the crosshair and a "
    "controlled background.":
        "測定課題を選んでください。課題中の画面には、ターゲット、クロスヘア、統制された背景のみが表示されます。",
    "Crosshair for this session": "このセッションのクロスヘア",
    "Controlled task-order assessment": "課題順序を統制した測定",
    "Start controlled assessment": "統制測定を開始",
    "Resume controlled assessment": "統制測定を再開",
    "Start another controlled assessment": "別の統制測定を開始",
    "Researcher/developer mode — individual task launch": "研究者・開発者モード — 課題の個別起動",
    "Non-experimental debugging only. These buttons do not constitute a controlled three-task assessment.":
        "実験外のデバッグ専用です。これらのボタンによる実行は、3課題を統制した測定にはなりません。",
    "Start": "開始",
    "No participant selected. Complete Player Setup before starting an assessment.":
        "参加者が選択されていません。測定を始める前に参加者設定を完了してください。",
    "Placeholder task parameters ({tasks}) from research_parameters.json. Sessions are usable for "
    "testing; confirm the parameters before collecting research data.":
        "research_parameters.json の課題パラメータ（{tasks}）は仮の値です。セッションは動作確認には使えますが、"
        "研究データを収集する前にパラメータを確定してください。",
    "Assigned experimental order: {assigned}. Fixed debug order: {debug}.":
        "割り当てられた本測定の順序: {assigned}。デバッグ用の固定順序: {debug}。",
    "Candidate #{crosshair_id} of recommendation #{recommendation_id} is not in the latest recommendation "
    "run; generate a new recommendation to try it.":
        "推薦 #{recommendation_id} の候補 #{crosshair_id} は最新の推薦結果に含まれていません。"
        "試すには新しく推薦を生成してください。",
    "Standard crosshair (baseline): {name}": "標準クロスヘア（ベースライン）: {name}",
    "Recommended candidate {rank} (recommendation #{recommendation_id}): {name}":
        "推薦候補 {rank}（推薦 #{recommendation_id}）: {name}",
    "My crosshair": "自分のクロスヘア",
    "Database (not from a recommendation)": "データベース（推薦によらない）",
    "from your latest recommendation": "最新の推薦から選択",
    "your own choice (not from a recommendation; stored without a recommendation id)":
        "自分で選択（推薦によらないため、推薦IDなしで保存）",
    "Re-test with this crosshair, {origin}. The session is recorded as condition “candidate” and linked "
    "to the {rule} for comparison. Task parameters are the same as the baseline; the target sequence uses "
    "the candidate seed.":
        "このクロスヘアで再測定します（{origin}）。セッションは条件「候補」として記録され、比較のため{rule}に"
        "紐付けられます。課題パラメータはベースラインと同じで、ターゲット系列には候補用のシードを使います。",
    "Other crosshairs can be chosen above; recommended candidates appear here after “Generate candidates” "
    "on the Recommendation page.":
        "上で他のクロスヘアも選べます。推薦ページで「候補を生成」を実行すると、推薦候補がここに表示されます。",
    "Baseline session with the standard crosshair. Your profile and recommendations use completed "
    "baseline sessions.":
        "標準クロスヘアによるベースラインセッションです。プロファイルと推薦には完了したベースラインセッションが"
        "使われます。",
    "Crosshair: standard (baseline)": "クロスヘア: 標準（ベースライン）",
    "Needs a completed baseline session of this task before a candidate re-test.":
        "候補での再測定の前に、この課題のベースラインセッションを完了する必要があります。",
    "Candidate re-test, compared with baseline session #{session_id}":
        "候補での再測定（ベースラインセッション #{session_id} と比較）",
    "Select a participant before starting.": "開始する前に参加者を選択してください。",
    "Next practice:\n{task}": "次の練習:\n{task}",
    "Next assessment:\n{task}": "次の測定:\n{task}",
    "Next practice: {task}": "次の練習: {task}",
    "Next assessment: {task}": "次の測定: {task}",
    "Controlled assessment complete.": "統制測定が完了しました。",
    "Practice tasks and experimental tasks will follow the participant's stored counterbalanced order.":
        "練習課題と本測定課題は、参加者に保存されたカウンターバランス順序に従って実施されます。",
    "The assessment crosshair no longer exists.": "測定用のクロスヘアが存在しません。",
    "A controlled candidate assessment needs completed baseline sessions for all three tasks. Missing: "
    "{tasks}.":
        "候補での統制測定には、3課題すべての完了済みベースラインセッションが必要です。不足: {tasks}。",
    "Run a completed baseline {task} session before this candidate task.":
        "この候補課題の前に、{task} のベースラインセッションを完了してください。",
    "Run a baseline {task} session first; a candidate re-test is compared with it.":
        "先に {task} のベースラインセッションを実施してください。候補での再測定はそれと比較されます。",
    "Session {session_id} {status}: {trials} trials saved.": "セッション {session_id}（{status}）: {trials} 試行を保存しました。",
    "Controlled assessment complete. All assigned tasks were recorded.":
        "統制測定が完了しました。割り当てられたすべての課題が記録されました。",
    "This participant already has an unfinished controlled assessment. Resume it before changing the "
    "condition or crosshair.":
        "この参加者には未完了の統制測定があります。条件やクロスヘアを変更する前に、それを再開してください。",
    "Next assessment: Crosshair evaluation": "次の測定: クロスヘア評価",
    "Crosshair evaluation — part {position} of 2": "クロスヘア評価 — 全2部のうち第{position}部",
    "Next familiarization:\n{task}": "次の慣熟:\n{task}",
    "Next familiarization: {task}": "次の慣熟: {task}",
    "Resume crosshair evaluation": "クロスヘア評価を再開",
    "Start crosshair evaluation part {position}": "クロスヘア評価の第{position}部を開始",
    "Rest before the next part: {seconds} s": "次の部の前の休憩: 残り {seconds} 秒",
    "Researcher view: evaluation #{evaluation_id}, order {group}, next condition {condition}":
        "研究者表示: 評価 #{evaluation_id}、順序 {group}、次の条件 {condition}",
    "Crosshair evaluation complete. All assigned tasks were recorded.":
        "クロスヘア評価が完了しました。割り当てられたすべての課題が記録されました。",
    "Part {position} of 2 complete. Next assessment: Crosshair evaluation":
        "全2部のうち第{position}部が完了しました。次の測定: クロスヘア評価",
    "Controlled post-baseline assessments run as a crosshair evaluation: select one candidate on the "
    "Recommendation page (“Select for crosshair evaluation”).":
        "ベースライン後の統制測定はクロスヘア評価として実施します。推薦ページで候補を1つ選んでください"
        "（「クロスヘア評価に選択」）。",
    "The stored standard crosshair no longer matches the baseline crosshair snapshot.":
        "保存されている標準クロスヘアが、ベースラインのクロスヘアスナップショットと一致しません。",
    "This crosshair evaluation is already complete.": "このクロスヘア評価はすでに完了しています。",
    "The crosshair of this condition no longer exists.": "この条件のクロスヘアが存在しません。",
    "This participant already has an unfinished crosshair evaluation.":
        "この参加者には未完了のクロスヘア評価があります。",
    "A candidate has already been selected for this recommendation run.":
        "この推薦ではすでに候補が選択されています。",
    "The candidate for this recommendation run is fixed by its crosshair evaluation.":
        "この推薦の候補はクロスヘア評価によって固定されています。",

    # ------------------------------------------------------------ experiment window
    "Practice complete. The experimental assessment will begin.": "練習が終わりました。本測定を始めます。",
    "Experimental Assessment": "本測定",
    "{count} trials": "{count} 試行",
    "Press Space to begin": "スペースキーで開始",
    "Press Space to continue": "スペースキーで続行",
    "Press Space to return": "スペースキーで戻る",
    "Practice": "練習",
    "Esc aborts": "Esc キーで中断",
    "Return to the centre and hold still": "中央に戻り、マウスを動かさないでください",
    "The mouse moved before the target appeared. This trial will be repeated.\n"
    "Click the centre and hold still until the target appears.":
        "ターゲットが表示される前にマウスが動きました。この試行はやり直します。\n"
        "中央をクリックし、ターゲットが表示されるまでマウスを動かさないでください。",
    "Practice: {count} trials (not analysed)": "練習: {count} 試行（分析対象外）",
    "Practice: {count} trials (not analysed), then": "練習: {count} 試行（分析対象外）、その後",
    "Experimental Assessment: {count} trials": "本測定: {count} 試行",
    "Crosshair: candidate ({name})": "クロスヘア: 候補（{name}）",
    "(Task parameters are placeholders and not yet confirmed)": "（課題パラメータは仮の値で、まだ確定していません）",
    "Practice complete: {count} trials saved for audit (not analysed)":
        "練習が完了しました: 確認用に {count} 試行を保存しました（分析対象外）",
    "Familiarization": "慣熟",
    "Familiarization: {count} trials (not analysed)": "慣熟: {count} 試行（分析対象外）",
    "Familiarization complete: {count} trials saved for audit (not analysed)":
        "慣熟が完了しました: 確認用に {count} 試行を保存しました（分析対象外）",
    "Researcher view: condition {condition}, order {group}, crosshair {name}":
        "研究者表示: 条件 {condition}、順序 {group}、クロスヘア {name}",
    "Session ended. No experimental trials were recorded.\n\nPress Space to return":
        "セッションを終了しました。本測定の試行は記録されていません。\n\nスペースキーで戻る",
    "  ·  {count} invalid (moved before the target) repeated": "  ·  無効 {count} 件（ターゲット表示前の移動）をやり直し",
    "Session complete: {count} trials saved{invalid}": "セッション完了: {count} 試行を保存{invalid}",
    "Session aborted: {count} trials saved{invalid}": "セッション中断: {count} 試行を保存{invalid}",
    "hits {hits}  ·  misses {misses}  ·  timeouts {timeouts}":
        "ヒット {hits}  ·  ミス {misses}  ·  タイムアウト {timeouts}",
    "No participant selected.": "参加者が選択されていません。",
    "No practice trials are configured for this task.": "この課題には練習試行が設定されていません。",
    "Could not save trial: {error}\nThe session is aborted.": "試行を保存できませんでした: {error}\nセッションを中断します。",
    "Abort session": "セッションの中断",
    "Abort this session? Completed trials stay saved and the session is marked as aborted.":
        "このセッションを中断しますか？完了した試行は保存されたまま残り、セッションは「中断」として記録されます。",
    "Click the grey circle in the centre and hold the mouse still.":
        "中央の灰色の円をクリックし、マウスを動かさずに待ってください。",
    "A red target then appears. Move the crosshair onto it and click":
        "赤いターゲットが表示されたら、クロスヘアを合わせてクリックしてください。",
    "as quickly and accurately as possible. One click per trial.":
        "できるだけ速く正確に。1試行につきクリックは1回です。",
    "A red target appears there and starts moving.": "そこに赤いターゲットが表示され、動き始めます。",
    "Keep the crosshair on the target for {seconds} seconds. No clicking is needed.":
        "{seconds} 秒間、クロスヘアをターゲットに合わせ続けてください。クリックは不要です。",
    "time on target (mean of trials): {percent} %": "ターゲット上の時間（試行の平均）: {percent} %",
    "{count} targets then appear. Click the red one; the next target":
        "続いて {count} 個のターゲットが表示されます。赤いターゲットをクリックすると、",
    "turns red immediately. One click per target, as quickly and accurately as possible.":
        "すぐに次のターゲットが赤くなります。1ターゲットにつき1回、できるだけ速く正確にクリックしてください。",

    # ------------------------------------------------------------ results
    "Measured results of one session, recomputed from the raw trial data. Values describe this session "
    "only; they are not norms or ratings.":
        "1セッションの測定結果です。生の試行データから再計算しています。値はこのセッションのみを表すもので、"
        "基準値や評価ではありません。",
    "Session": "セッション",
    "Export CSV / JSON": "CSV / JSON を出力",
    "Session metrics": "セッションの指標",
    "Analysis version {version}. Medians for times; completion and switching times use hit trials only; "
    "click error uses hits and misses.":
        "分析バージョン {version}。時間は中央値です。完了時間とスイッチング時間はヒット試行のみ、"
        "クリック誤差はヒットとミスを使用します。",
    "Per-trial chart": "試行ごとのグラフ",
    "#": "#",
    "Target": "ターゲット",
    "Result": "結果",
    "Reaction (ms)": "反応時間 (ms)",
    "Completion (ms)": "完了時間 (ms)",
    "Click error (px)": "クリック誤差 (px)",
    "Target distance (px)": "ターゲット距離 (px)",
    "Moved at onset": "提示時に移動中",
    "Validity": "有効性",
    "Trial": "試行",
    "Time on target": "ターゲット上の時間",
    "Mean distance (px)": "平均距離 (px)",
    "RMS distance (px)": "RMS距離 (px)",
    "yes": "はい",
    "no": "いいえ",
    "No sessions recorded for participant {player_id} yet. Run an assessment first.":
        "参加者 {player_id} のセッションはまだ記録されていません。先に測定を実施してください。",
    "No sessions recorded yet. Run an assessment first.":
        "セッションはまだ記録されていません。先に測定を実施してください。",
    "Could not analyse session {session_id}: {error}": "セッション {session_id} を分析できませんでした: {error}",
    "Session status: {status}. Metrics use the trials that were saved.":
        "セッションの状態: {status}。指標は保存された試行から計算しています。",
    "{count} recomputed values differ from the values stored during recording (first: {first}).":
        "再計算した値のうち {count} 件が記録時に保存された値と異なります（最初の例: {first}）。",
    "{count} rows from restarted switching trials are excluded (latest attempt used).":
        "やり直したスイッチング試行の {count} 行を除外しています（最新の試行を使用）。",
    "{count} trials were invalidated because the mouse moved before the target appeared; they were "
    "repeated and are excluded from all metrics.":
        "ターゲット表示前にマウスが動いたため {count} 試行が無効になりました。これらはやり直され、"
        "すべての指標から除外されています。",
    "{count} trials used the {ms} ms timing fallback (target onset not confirmed by a paint); they are "
    "excluded from time measures.":
        "{count} 試行で {ms} ms のタイミング代替処理が使われました（描画によるターゲット提示の確認なし）。"
        "これらは時間の指標から除外されています。",
    "{count} trials recomputed from raw samples and events; all match the recorded values.":
        "{count} 試行を生のサンプルとイベントから再計算しました。すべて記録時の値と一致しています。",
    "Protocol: {protocol}.": "プロトコル: {protocol}。",
    "not recorded (session before protocol versioning)": "未記録（プロトコルのバージョン管理導入前のセッション）",
    ", position {position}/3": "、{position}/3 番目",
    "Task order: {order} (group {group}{position}).": "課題順序: {order}（グループ {group}{position}）。",
    "not recorded": "未記録",
    "Task order: not recorded (historical session).": "課題順序: 未記録（過去のセッション）。",
    "{count} practice trials are listed for audit but are not analysed.":
        "練習 {count} 試行は確認用に表示していますが、分析には含めていません。",
    "The crosshair was moving at target onset in {percent} % of trials, so reaction time mostly reflects "
    "ongoing movement rather than a response to the target.":
        "{percent} % の試行でターゲット提示時にクロスヘアが動いていたため、反応時間はターゲットへの反応より"
        "継続中の動きを主に反映しています。",
    "time on target (%)": "ターゲット上の時間 (%)",
    "Time on target per trial": "試行ごとのターゲット上の時間",
    "completion time (ms)": "完了時間 (ms)",
    "Completion time per trial": "試行ごとの完了時間",
    "Time per target (first target and switches)": "ターゲットごとの時間（最初のターゲットと切り替え）",
    "trial": "試行",
    "Export failed: {error}": "出力に失敗しました: {error}",
    "Exported to {folder}": "{folder} に出力しました",
    # validity labels (metrics.TrialAnalysis.validity_label)
    "invalid: moved before target": "無効: ターゲット表示前に移動",
    "timing fallback": "タイミング代替処理",
    "valid (RT excluded: moving at onset)": "有効（反応時間は除外: 提示時に移動中）",

    # ------------------------------------------------------------ metrics (labels / descriptions)
    "Trials (or targets) analysed": "分析した試行（またはターゲット）",
    "Hit rate": "ヒット率",
    "Hits / trials": "ヒット数 / 試行数",
    "Timeout rate": "タイムアウト率",
    "Timeouts / trials": "タイムアウト数 / 試行数",
    "Reaction time (median)": "反応時間（中央値）",
    "t0 -> movement onset": "t0 → 動き始め",
    "Completion time (median, hits)": "完了時間（中央値・ヒット）",
    "Completion time (mean, hits)": "完了時間（平均・ヒット）",
    "t0 -> click, hit trials": "t0 → クリック（ヒット試行）",
    "Click error (mean)": "クリック誤差（平均）",
    "Crosshair-to-target-centre distance at the click": "クリック時のクロスヘアとターゲット中心の距離",
    "Click error / target radius (mean)": "クリック誤差 / ターゲット半径（平均）",
    "1.0 = edge of the target": "1.0 = ターゲットの縁",
    "Time on target (mean)": "ターゲット上の時間（平均）",
    "Share of trial time within the target radius": "試行時間のうちターゲット半径内にあった割合",
    "Distance to target (mean)": "ターゲットまでの距離（平均）",
    "Time-weighted crosshair-to-target distance": "時間で重み付けしたクロスヘアとターゲットの距離",
    "Distance to target (RMS, mean)": "ターゲットまでの距離（RMS・平均）",
    "Time-weighted root-mean-square distance": "時間で重み付けした二乗平均平方根距離",
    "Switching time (median, hits)": "スイッチング時間（中央値・ヒット）",
    "Previous click -> click on the next target": "前のクリック → 次のターゲットのクリック",
    "First-target time (median, hits)": "最初のターゲットまでの時間（中央値・ヒット）",
    "t0 -> click on the first target": "t0 → 最初のターゲットのクリック",
    "Moving at target onset": "ターゲット提示時に移動中",
    "Trials where the crosshair moved in the 100 ms before t0; their reaction time is excluded":
        "t0 前の 100 ms にクロスヘアが動いた試行。これらの反応時間は除外されます",
    "Trials valid for reaction time": "反応時間に有効な試行",
    "Valid status, movement onset detected, not moving at target onset":
        "有効な状態で、動き始めを検出し、ターゲット提示時に動いていない試行",
    "Invalid trials (moved before target)": "無効な試行（ターゲット表示前に移動）",
    "Trials invalidated because the cursor moved during the foreperiod; repeated, excluded from all metrics":
        "予告期間中にカーソルが動いたため無効になった試行。やり直され、すべての指標から除外されます",
    "Timing-fallback trials": "タイミング代替処理の試行",
    "Target onset taken from the fallback timer; excluded from time measures, kept for accuracy":
        "ターゲット提示時刻を代替タイマーから取得した試行。時間の指標からは除外し、正確性の指標には含めます",
    "Practice trials (not analysed)": "練習試行（分析対象外）",
    "Practice rows stored for audit; excluded from every metric, the profile and comparisons":
        "確認用に保存した練習の行。すべての指標、プロファイル、比較から除外されます",

    # ------------------------------------------------------------ recommendation
    "Candidate crosshairs to try next, ranked by a rule-based score from your own baseline measurements. "
    "This is not a validated prediction: only a re-test can show a measured difference.":
        "次に試すクロスヘア候補です。自分のベースライン測定に基づくルールベースのスコアで順位付けしています。"
        "これは検証済みの予測ではありません。測定上の差は再測定によってのみ確認できます。",
    "Generate candidates": "候補を生成",
    "Stored runs": "保存済みの推薦",
    "Your baseline profile": "あなたのベースラインプロファイル",
    "Source rule: {rule} (placeholder). Aborted, practice, familiarization, standard and candidate "
    "sessions are not used.":
        "使用するデータ: {rule}（仮の規則）。中断、練習、慣熟、標準条件、候補条件のセッションは使いません。",
    "initial completed baseline session per task": "課題ごとの最初の完了済みベースラインセッション",
    "A crosshair evaluation already uses a recommendation run of this participant. The recommendation is "
    "generated once per cycle and later sessions do not change it.":
        "この参加者の推薦はすでにクロスヘア評価で使われています。推薦は1サイクルにつき1回だけ生成され、"
        "その後のセッションによって変わることはありません。",
    "Select for crosshair evaluation": "クロスヘア評価に選択",
    "Selected for crosshair evaluation": "クロスヘア評価に選択済み",
    "Use this crosshair for the crosshair evaluation? The selection cannot be changed afterwards.":
        "このクロスヘアをクロスヘア評価に使いますか？選択は後から変更できません。",
    "Candidate selected. Next assessment: Crosshair evaluation": "候補を選択しました。次の測定: クロスヘア評価",
    "Rules (placeholder hypotheses, not validated)": "ルール（仮説段階で未検証）",
    "Candidates to try": "試す候補",
    "({version}, {count} candidates)": "（{version}、候補 {count} 件）",
    "Select or create a participant on the Setup page first.": "先に参加者設定ページで参加者を選択または作成してください。",
    "No recommendation generated yet for participant {player_id}. Complete at least one baseline "
    "assessment, then press “Generate candidates”.":
        "参加者 {player_id} の推薦はまだ生成されていません。ベースライン測定を1つ以上完了してから"
        "「候補を生成」を押してください。",
    "No completed baseline session yet. Run at least one assessment with the standard crosshair first.":
        "完了したベースラインセッションがまだありません。先に標準クロスヘアで測定を1つ以上実施してください。",
    "The crosshair database has no candidates that differ from the baseline. Import or update candidates "
    "on the Crosshair page first.":
        "クロスヘアデータベースにベースラインと異なる候補がありません。先にクロスヘアページで候補を取り込むか"
        "更新してください。",
    "Could not generate candidates: {error}": "候補を生成できませんでした: {error}",
    "No completed baseline session for: {names}. Rules that need these tasks were not applied. Run those "
    "assessments and generate again to include them.":
        "完了したベースラインセッションがない課題: {names}。これらの課題が必要なルールは適用されていません。"
        "含めるには、その測定を実施してから再度生成してください。",
    "Method: {method} ({version}). Components, weights, thresholds and rules are configurable in "
    "research_parameters.json and have not been validated.":
        "手法: {method}（{version}）。要素、重み、しきい値、ルールは research_parameters.json で設定でき、"
        "まだ検証されていません。",
    "Research decision required: these are placeholder values (confirmed = false).":
        "研究上の判断が必要です: これらは仮の値です（confirmed = false）。",
    "no completed baseline session": "完了したベースラインセッションなし",
    "Session {session_id}": "セッション {session_id}",
    "Rule": "ルール",
    "Condition": "条件",
    "Your value": "あなたの値",
    "Weight change": "重みの変更",
    "Status": "状態",
    "Applied": "適用",
    "Not applied": "非適用",
    "No data": "データなし",
    "no data": "データなし",
    "applied": "適用",
    "not applied": "非適用",
    " ({count} excluded as duplicates)": "（重複として {count} 件を除外）",
    "Weights used: {weights}. Candidate pool: {pool} crosshairs{excluded}. Score = weighted mean of the "
    "component scores (0–1).":
        "使用した重み: {weights}。候補プール: クロスヘア {pool} 件{excluded}。スコア = 各要素スコアの加重平均（0〜1）。",
    "visibility": "視認性",
    "centre precision": "中心の精度",
    "low occlusion": "遮蔽の少なさ",
    "source fidelity": "出典の再現度",
    "This run has no candidates.": "この推薦には候補がありません。",
    "Candidate {rank}: {name}": "候補 {rank}: {name}",
    "  (selected to try)": "  （試用に選択済み）",
    "from {player}": "{player} のもの",
    "source: {name}": "出典: {name}",
    "mapping fidelity: {fidelity}": "変換の再現度: {fidelity}",
    "n/a": "該当なし",
    "Candidate score {score}": "候補スコア {score}",
    "Try this candidate": "この候補を試す",
    "{component} {score} (weight {weight})": "{component} {score}（重み {weight}）",
    "Score {score} = weighted mean of {parts}.": "スコア {score} = {parts} の加重平均。",
    "Rules that changed the weights: {rules}.": "重みを変更したルール: {rules}。",
    "No rule changed the base weights.": "基本の重みを変更したルールはありません。",

    # ------------------------------------------------------------ comparison
    "Measured differences between a candidate re-test session and the baseline session it is linked to. "
    "Differences describe these two sessions only.":
        "候補での再測定セッションと、紐付けられたベースラインセッションの測定上の差です。差はこの2つの"
        "セッションのみを表します。",
    "Candidate session": "候補セッション",
    "Export CSV": "CSV を出力",
    "Sessions compared": "比較したセッション",
    "Metrics": "指標",
    "Metric": "指標",
    "Baseline": "ベースライン",
    "Candidate": "候補",
    "Difference (candidate − baseline)": "差（候補 − ベースライン）",
    "% difference": "差 (%)",
    "Measured direction": "測定された方向",
    "Desirable direction": "望ましい方向",
    "Analysis version {version}. pp = percentage points. “% difference” is only given for times and "
    "distances. “Desirable direction” states which direction the metric is defined to favour; it is not "
    "a judgement of the crosshair.":
        "分析バージョン {version}。pp = パーセントポイント。「差 (%)」は時間と距離にのみ示します。"
        "「望ましい方向」は指標の定義上どちらの方向が望ましいかを示すもので、クロスヘアの評価ではありません。",
    "Per-trial values": "試行ごとの値",
    "No candidate sessions yet. On the Recommendation page choose “Try this candidate”, then run the same "
    "task again on the Aim Assessment page; the session will appear here next to its baseline.":
        "候補セッションはまだありません。推薦ページで「この候補を試す」を選び、エイム測定ページで同じ課題を"
        "もう一度実施すると、そのセッションがベースラインと並んでここに表示されます。",
    "vs baseline #{session_id}": "ベースライン #{session_id} と比較",
    "Could not compare session {session_id}: {error}": "セッション {session_id} を比較できませんでした: {error}",
    "Caveats:": "注意事項:",
    "Session #{session_id}": "セッション #{session_id}",
    "Crosshair: {name}": "クロスヘア: {name}",
    "Status: {status}  ·  {count} trials": "状態: {status}  ·  {count} 試行",
    "From recommendation #{recommendation_id}": "推薦 #{recommendation_id} から",
    "Open results": "結果を開く",
    "Baseline (standard crosshair)": "ベースライン（標準クロスヘア）",
    "trial / target (order in session)": "試行 / ターゲット（セッション内の順番）",
    "completion time, hits (ms)": "完了時間・ヒット (ms)",
    "Completion time per hit": "ヒットごとの完了時間",
    "higher": "高い方",
    "lower": "低い方",
    "no measured difference": "測定上の差なし",
    "higher with candidate": "候補の方が高い",
    "lower with candidate": "候補の方が低い",
    "Descriptive comparison of two single sessions. No statistical test was performed; differences may be "
    "within normal session-to-session variation.":
        "2つの単一セッションの記述的な比較です。統計的検定は行っていません。差は通常のセッション間の"
        "ばらつきの範囲内である可能性があります。",
    "The candidate session was recorded after the baseline session with the same target sequence, so "
    "practice or familiarity can contribute to any difference (order effect).":
        "候補セッションは同じターゲット系列でベースラインセッションの後に記録されたため、練習や慣れが差に"
        "影響している可能性があります（順序効果）。",
    "The two sessions were recorded with different timing procedures (e.g. one without the pre-trial "
    "stabilization period), so their time measures are not directly comparable.":
        "2つのセッションは異なるタイミング手順で記録されています（例: 一方は試行前の静止期間なし）。そのため"
        "時間の指標は直接比較できません。",
    "Task parameters or the arena size differ between the two sessions, so the target sequences are not "
    "identical.":
        "2つのセッションで課題パラメータまたは表示領域のサイズが異なるため、ターゲット系列は同一ではありません。",
    "Task parameters are placeholders (confirmed = false).": "課題パラメータは仮の値です（confirmed = false）。",
    "The candidate session was recorded after the baseline session, so practice or familiarity can "
    "contribute to any difference (order effect). It used a different seed (same task parameters, "
    "different target sequence); the seeds are not claimed to be equivalent in difficulty.":
        "候補セッションはベースラインセッションの後に記録されたため、練習や慣れが差に影響している可能性があります"
        "（順序効果）。候補セッションは別のシードを使用しています（課題パラメータは同じで、ターゲット系列が異なる）。"
        "シード間で難易度が等しいとは主張しません。",
    # three-condition comparison (Phase 5)
    "Crosshair evaluation: three conditions": "クロスヘア評価: 3条件の比較",
    "Evaluation": "評価",
    "Evaluation #{evaluation_id}  ·  recommendation #{recommendation_id}  ·  {status}":
        "評価 #{evaluation_id}  ·  推薦 #{recommendation_id}  ·  {status}",
    "Could not compare evaluation {evaluation_id}: {error}": "評価 {evaluation_id} を比較できませんでした: {error}",
    "Order {group} ({order})  ·  selected candidate #{candidate}  ·  protocol {protocol}":
        "順序 {group}（{order}）  ·  選択した候補 #{candidate}  ·  プロトコル {protocol}",
    "Descriptive differences of single sessions only (no statistical test). “%” is only given for times "
    "and distances; pp = percentage points.":
        "単一セッション間の記述的な差のみです（統計的検定なし）。「%」は時間と距離にのみ示します。"
        "pp = パーセントポイント。",
    "Standard": "標準",
    "Baseline → Standard": "ベースライン → 標準",
    "Baseline → Candidate": "ベースライン → 候補",
    "Standard → Candidate": "標準 → 候補",
    "higher with standard": "標準の方が高い",
    "lower with standard": "標準の方が低い",
    "{other} condition was {amount} higher than {reference} condition.":
        "{other}条件は{reference}条件より{amount}高かった。",
    "{other} condition was {amount} lower than {reference} condition.":
        "{other}条件は{reference}条件より{amount}低かった。",
    "{other} condition showed no measured difference from {reference} condition.":
        "{other}条件と{reference}条件の間に測定上の差はなかった。",
    "No data for {other} or {reference} condition.": "{other}条件または{reference}条件のデータがありません。",
    "Descriptive comparison of single sessions. No statistical test was performed; differences may be "
    "within normal session-to-session variation.":
        "単一セッションの記述的な比較です。統計的検定は行っていません。差は通常のセッション間のばらつきの範囲内で"
        "ある可能性があります。",
    "Standard repeats the baseline crosshair; a Baseline–Standard difference can arise without any "
    "crosshair change (repetition or session-to-session variation).":
        "標準条件はベースラインと同じクロスヘアを繰り返します。ベースラインと標準の差は、クロスヘアを変えなくても"
        "（繰り返しやセッション間のばらつきにより）生じ得ます。",
    "Each condition used a different seed (same task parameters, different target sequence); the seeds "
    "are not claimed to be equivalent in difficulty.":
        "各条件は異なるシードを使用しています（課題パラメータは同じで、ターゲット系列が異なる）。シード間で難易度が"
        "等しいとは主張しません。",
    "Practice and familiarization trials are excluded from all metrics.":
        "練習と慣熟の試行はすべての指標から除外されます。",
    "The sessions were recorded with different timing procedures, so their time measures are not directly "
    "comparable.":
        "セッションは異なるタイミング手順で記録されているため、時間の指標は直接比較できません。",
    "Task parameters or the arena size differ between the sessions.":
        "セッション間で課題パラメータまたは表示領域のサイズが異なります。",

    # ------------------------------------------------------------ history
    "All recorded sessions. Aborted sessions are kept; raw trial data is never deleted. Double-click a "
    "session to open it (candidate sessions open the comparison).":
        "記録されたすべてのセッションです。中断したセッションも保持され、生の試行データは削除されません。"
        "セッションをダブルクリックすると開きます（候補セッションは比較を開きます）。",
    "No sessions recorded yet. Sessions will appear here after an assessment is run.":
        "セッションはまだ記録されていません。測定を実施するとここに表示されます。",
    "Recommendation history": "推薦の履歴",
    "No recommendation runs yet.": "推薦はまだ実行されていません。",
    "Started (UTC)": "開始 (UTC)",
    "Task": "課題",
    "Task order": "課題順序",
    "Position": "順番",
    "Phase": "段階",
    "Session #": "セッション番号",
    "Run": "推薦",
    "Created (UTC)": "作成 (UTC)",
    "Method": "手法",
    "Based on sessions": "使用したセッション",
    "Candidates (rank: name)": "候補（順位: 名前）",
    "Selected to try": "試用に選択",

    # ------------------------------------------------------------ settings
    "Storage locations and software versions.": "保存場所とソフトウェアのバージョン。",
    "Storage": "保存場所",
    "Exports": "出力",
    "Raw data": "生データ",
    "Logs": "ログ",
    "Open data folder": "データフォルダを開く",
    "Versions": "バージョン",
    "Application": "アプリケーション",
    "Database schema": "データベーススキーマ",

    # ------------------------------------------------------------ placeholders
    "Not yet available": "未実装",
    "This screen will be implemented in {milestone}.": "この画面は {milestone} で実装予定です。",
    "Planned contents:": "予定している内容:",
}
