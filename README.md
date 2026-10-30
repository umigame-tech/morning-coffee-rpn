# Crema ☕

**Crema** は逆ポーランド記法 (RPN) を採用した、スタックベースの汎用プログラミング言語です。
値を先に書き、操作を後に書きます。

```crema
: fib ( n -- fib(n) )
  dup 2 < [ ] [ dup 1 - fib swap 2 - fib + ] if ;

0 10 [ -> i  "fib({}) = {}" { i i fib } printfln ] for
```

- スタックベースの実行モデル
- ユーザー定義関数 (`: name ... ;`)、再帰、相互再帰、末尾呼び出し最適化
- 条件分岐 (`if` / `when` / `unless` / `?`)
- ループ (`while` / `times` / `for` / `for-step` / `each` / `loop` + `break`)
- 数値 (任意精度整数・浮動小数点数)、文字列、リスト、辞書、クォート (コードブロック)
- ファイルの読み書き、標準入力、コマンドライン引数
- 例外処理 (`try` / `throw`)、エラー位置とコールトレースの表示
- CLI (ファイル実行・`-e` によるワンライナー・REPL)

実装は Python 3.8+ の標準ライブラリだけで動作し、依存パッケージはありません。

## 使い方

```sh
# インストールせずに使う
bin/crema examples/hello.crema

# インストールする場合 (crema コマンドが入ります)
pip install .
crema examples/hello.crema
```

```
crema FILE [ARGS...]     プログラムを実行 (ARGS は args で取得)
crema -                  標準入力からプログラムを読んで実行
crema -e 'CODE' [ARGS]   コードを直接実行
crema -i FILE            実行後に REPL に入る
crema                    REPL を起動
```

`#!/usr/bin/env crema` で始めればスクリプトとして直接実行することもできます。
エラーが起きると `ファイル:行:桁` とコールトレースを表示して終了コード 1 で終わります。

## 言語ガイド

### 基本

プログラムは空白区切りの「ワード」の並びです。数値や文字列はスタックに積まれ、
ワードはスタックから値を取り出して結果を積みます。

```crema
1 2 + 3 *       # => 9
"abc" upper     # => "ABC"
# 行コメント
( スタック効果コメント: a b -- c )
```

| リテラル | 例 |
|---|---|
| 整数 | `42` `-7` `0xff` (任意精度) |
| 浮動小数点数 | `3.14` `1e-3` |
| 文字列 | `"hello\n"` (エスケープ: `\n \t \r \" \\ \0 \e \u{3042}`) |
| 真偽値・nil | `true` `false` `nil` |
| クォート | `[ dup * ]` 実行されないコードブロック (クロージャ) |
| リスト | `{ 1 2 + 4 }` → `{3 4}` 中身を実行して積まれた値を集める |
| 辞書 | `#{ "a" 1 "b" 2 }` キーと値の組を集める |

偽になるのは `false` と `nil` だけです (`0` や `""` は真)。

### 変数

`-> name` でスタックのトップを変数に取り出します。名前を書くと値が積まれます。
変数は関数呼び出しごとのローカルスコープで、トップレベルで束縛したものはグローバルです。
クォートは作られた場所のスコープを捕捉します (クロージャ)。

```crema
10 -> x
x x * println                 # 100

: adder ( n -- [q] ) -> n [ n + ] ;
5 adder -> add5
10 add5 call println          # 15
```

### 関数

```crema
: square ( n -- n*n ) dup * ;
: sum-to ( n -- total ) dup 0 = [ ] [ dup 1 - sum-to + ] if ;
```

- 定義はファイル内で巻き上げられるので、定義順や相互再帰を気にする必要はありません。
- 末尾位置の呼び出しはスタックを消費しません (無限の末尾再帰ループも可)。
- 末尾でない再帰も Python のスタックを使わないため、深さ 100 万程度まで動きます。
- `"name" [ body ] def` で実行時に関数を定義できます。`"code" eval` で文字列を実行できます。
- `"lib.crema" include` で別ファイルを読み込みます (読み込み元からの相対パス)。

### 条件分岐

```crema
x 0 < [ "negative" ] [ "non-negative" ] if println
x even? [ "even" println ] when
x even? [ "odd" println ] unless
x 0 > "pos" "non-pos" ? println        # 値を選ぶだけなら ?
```

### ループ

```crema
[ i 10 < ] [ i println  i 1 + -> i ] while   # [条件] [本体] while
3 [ "hi" println ] times                      # n [本体] times
0 5 [ println ] for                           # 0 1 2 3 4 (終端は含まない)
10 0 -2 [ println ] for-step                  # 10 8 6 4 2
{ "a" "b" } [ println ] each                  # リスト・文字列・辞書 ({k v} の組)
[ ... dup 100 > [ break ] when ] loop         # break で最も内側のループを抜ける
```

### 例外

```crema
[ 1 0 / ] [ "error: " swap + println ] try    # ハンドラはエラーメッセージを受け取る
"something went wrong" throw
x 0 >= "x must be non-negative" assert
```

`try` はエラー時にスタックの深さを本体実行前の状態に戻してからハンドラを呼びます。

## ワード一覧

スタック効果は `( 前 -- 後 )` の形で表しています。

**スタック**: `dup` `drop` `swap` `over` `rot` (a b c -- b c a) `-rot` `nip` `tuck` `pick` (n -- x) `2dup` `2drop` `depth` `clear` `.s` `dip` `keep` `bi`

**算術**: `+` `-` `*` `/` (割り切れれば整数) `div` (切り捨て除算) `mod` `%` `**` `neg` `abs` `inc` `dec` `min` `max` `floor` `ceil` `round` `sqrt` `sin` `cos` `tan` `exp` `log` `pi` `random` `randint` (lo hi -- n) `even?` `odd?` `zero?` `square` `between?`

**比較・論理**: `=` `!=` `<` `>` `<=` `>=` `and` `or` `not` `?`

**制御**: `call` `if` `when` `unless` `while` `times` `for` `for-step` `each` `loop` `break` `try` `throw` `assert` `exit` `def` `eval` `include`

**型・変換**: `type` `str` `repr` `int` `float` `num` (文字列を数値に、失敗時 nil)

**文字列**: `len` `+` `*` (繰り返し) `upper` `lower` `trim` `split` (s sep -- list) `words` `lines` `join` (list sep -- s) `chars` `ord` `chr` `replace` (s old new -- s) `starts-with?` `ends-with?` `format` (`"{} + {}" {1 2} format`) `concat` `pad-left` `pad-right` (s width ch -- s) `printf` `printfln`

**リスト・辞書**: `get` (coll k -- v) `put` (coll k v -- coll) `append` `pop` `insert` `remove` `slice` (seq start end -- seq) `first` `last` `rest` `reverse` `sort` `sort-by` `range` (a b -- list) `copy` `contains?` `index-of` `empty?` `unpack` `pack` (... n -- list) `dict` `keys` `values` `map` `filter` `reject` `fold` (xs init [f] -- acc) `sum` `product` `max-of` `min-of` `count` `any?` `all?` `find` `each-with-index` `zip` `flatten` `uniq`

リストと辞書は参照型で、`put` `append` などは元のオブジェクトを変更します (必要なら `copy`)。

**入出力**: `print` `println` / `.` `cr` `eprintln` `read-line` (EOF で nil) `read-stdin` `read-file` (path -- s) `read-lines` `write-file` (s path --) `append-file` `file-exists?` `delete-file` `list-dir`

**システム**: `args` `now` `getenv` `exit` `words-list`

**テスト**: `assert-eq` (actual expected --) `assert-error` ([code] --)

高階関数・文字列ユーティリティなどの多くは Crema 自身で書かれています ([`crema/prelude.crema`](crema/prelude.crema))。

## サンプル

| ファイル | 内容 |
|---|---|
| [`examples/hello.crema`](examples/hello.crema) | Hello world、変数、format |
| [`examples/fib.crema`](examples/fib.crema) | 再帰・末尾再帰・多倍長整数 |
| [`examples/fizzbuzz.crema`](examples/fizzbuzz.crema) | 条件分岐と各種ループ |
| [`examples/quicksort.crema`](examples/quicksort.crema) | 再帰的クイックソートと高階関数 |
| [`examples/files.crema`](examples/files.crema) | ファイルの書き込み・追記・読み込み・集計 |
| [`examples/wc.crema`](examples/wc.crema) | 引数のファイルの行数・単語数・文字数を数える `wc` |
| [`examples/todo.crema`](examples/todo.crema) | ファイルに保存される TODO 管理 CLI |
| [`examples/calc.crema`](examples/calc.crema) | 辞書とクォートで作る対話型 RPN 電卓 |
| [`examples/brainfuck.crema`](examples/brainfuck.crema) | Crema で書いた Brainfuck インタプリタ |
| [`examples/errors.crema`](examples/errors.crema) | 例外処理 |

```sh
bin/crema examples/todo.crema add "コーヒー豆を買う"
bin/crema examples/todo.crema list
echo "3 4 + 2 *" | bin/crema examples/calc.crema
```

## テスト

```sh
python3 -m unittest discover -s tests -t .
```

言語機能のテストの多くは Crema 自身で書かれています ([`tests/lang/`](tests/lang))。
単体でも `bin/crema tests/lang/core.crema` のように実行できます。

## 実装の概要

| ファイル | 役割 |
|---|---|
| `crema/parser.py` | 字句解析・構文解析 (定義・クォート・リスト/辞書リテラル・変数束縛) |
| `crema/vm.py` | 実行エンジン。Python の再帰を使わず、フレームとタスクの明示的なスタックで実行するため、深い再帰・末尾呼び出し最適化・`try`/`break` の巻き戻しが可能 |
| `crema/builtins.py` | Python で実装した組み込みワード |
| `crema/prelude.crema` | Crema で書かれた標準ライブラリ |
| `crema/cli.py` | コマンドラインと REPL |
