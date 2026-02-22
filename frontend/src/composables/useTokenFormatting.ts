/**
 * Shared formatting functions for token usage display across monitoring sub-components.
 */
export function useTokenFormatting() {
  function formatCurrency(value: number): string {
    return `$${value.toFixed(2)}`;
  }

  function formatTokenCount(n: number): string {
    if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + 'B';
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
    return n.toString();
  }

  function parseWindowType(windowType: string): { model: string; window: string } {
    // Codex: "GPT-5.3-Codex_primary_window" or "GPT-5.3-Codex-Spark_secondary_window"
    const codexMatch = windowType.match(/^(.+?)_(primary|secondary)_window$/);
    if (codexMatch) {
      return { model: codexMatch[1], window: codexMatch[2] === 'primary' ? '5 Hour' : '7 Day' };
    }
    // Claude windows
    if (windowType === 'five_hour' || windowType === '5h_sliding')
      return { model: 'Opus', window: '5 Hour' };
    if (windowType === 'seven_day' || windowType === 'weekly')
      return { model: 'Opus', window: '7 Day' };
    if (windowType === 'seven_day_sonnet') return { model: 'Sonnet', window: '7 Day' };
    // Gemini: model name IS the window type
    return { model: windowType, window: '' };
  }

  return { formatCurrency, formatTokenCount, parseWindowType };
}
