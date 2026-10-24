<script>
  let {panel} = $props();
  let info = $derived(panel.metadata);
</script>

<div class="pi-status" aria-label="pi 会话状态" role="status">
  <span class="pi-mark">pi</span>
  <span class="state" class:working={panel.busy}>{panel.busy ? info.Pi状态 || '准备中' : '就绪'}</span>
  {#if info.Pi会话}<span class="session" title={info.Pi会话}>会话 {info.Pi会话.slice(0,8)}</span>{/if}
  <span class="spacer"></span>
  {#if info.首字秒 !== undefined}<span>首字 {info.首字秒} s</span>{/if}
  {#if info.每秒tokens}<span>{info.每秒tokens} tokens/s</span>{/if}
  {#if info.输出tokens}<span>{info.输出tokens} tokens</span>{/if}
</div>

<style>
  .pi-status{display:flex;align-items:center;flex-wrap:wrap;gap:10px;padding:9px 18px;border-bottom:1px solid #eceef1;color:#75808e;font-size:11px;}
  .pi-mark{background:#202b36;color:white;font-size:14px;font-weight:650;border-radius:5px;padding:1px 7px;}
  .state{color:#4d6a58;}.state.working{color:#ae662f;}.spacer{flex:1;}
  .session{font-family:ui-monospace,monospace;color:#8c949e;}
</style>
