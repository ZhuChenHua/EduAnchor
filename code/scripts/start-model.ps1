param(
    [int]$Port = 8081
)

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$server = Join-Path $root 'runtime\llama\llama-server.exe'
$model = Join-Path $root 'models\Qwen3-8B-GGUF\Qwen3-8B-Q4_K_M.gguf'

if (-not (Test-Path -LiteralPath $server)) {
    throw "Missing $server. See docs/DEPLOYMENT.md for the bundled runtime."
}
if (-not (Test-Path -LiteralPath $model)) {
    throw "Missing $model. Download Qwen/Qwen3-8B-GGUF from ModelScope."
}

& $server -m $model --alias qwen3-8b --host 127.0.0.1 --port $Port `
    -c 8192 -ngl 99 --jinja --reasoning off --no-webui
