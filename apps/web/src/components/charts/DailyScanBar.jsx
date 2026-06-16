// 柱状图:每日扫描 / 异常数量(PassengerOBUMonitor 替换原 CSS 柱状图)
import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'

const PRIMARY = '#5180FF'
const DANGER = '#D84C57'
const TEXT_PRIMARY = '#191C1E'
const TEXT_SECONDARY = '#667085'
const BORDER = 'rgba(25,28,30,0.12)'

export default function DailyScanBar({ data = [] }) {
  const option = useMemo(() => {
    const dates = data.map(d => d.date.slice(5))
    const scanned = data.map(d => d.scanned_count || 0)
    const suspicious = data.map(d => d.suspicious_count || 0)
    return {
      grid: { top: 28, right: 16, bottom: 28, left: 40, containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: '#FFFFFF',
        borderColor: BORDER,
        borderWidth: 1,
        padding: [10, 14],
        textStyle: { color: TEXT_PRIMARY, fontFamily: 'Inter, "PingFang SC", sans-serif', fontSize: 12 },
        extraCssText: 'box-shadow: 0 14px 40px -12px rgba(25,28,30,0.10); border-radius: 14px;',
        formatter: (params) => {
          if (!params || params.length === 0) return ''
          const idx = params[0].dataIndex
          const d = data[idx]
          const lines = [
            `<div style="font-weight:600;margin-bottom:4px">${d.date}</div>`,
            `<div>扫描: ${d.scanned_count || 0}</div>`,
            `<div style="color:${DANGER}">异常: ${d.suspicious_count || 0}</div>`,
          ]
          return lines.join('')
        },
      },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine: { lineStyle: { color: BORDER } },
        axisTick: { show: false },
        axisLabel: { color: TEXT_SECONDARY, fontSize: 10, fontFamily: 'Inter, "PingFang SC", sans-serif' },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: 'rgba(25,28,30,0.06)' } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: TEXT_SECONDARY, fontSize: 11, fontFamily: 'Inter, "PingFang SC", sans-serif' },
      },
      series: [
        {
          name: '扫描',
          type: 'bar',
          stack: 'count',
          barWidth: 14,
          itemStyle: {
            color: PRIMARY,
            borderRadius: [3, 3, 0, 0],
          },
          data: scanned,
        },
        {
          name: '异常',
          type: 'bar',
          stack: 'count',
          barWidth: 14,
          itemStyle: {
            color: DANGER,
            borderRadius: [3, 3, 0, 0],
          },
          data: suspicious,
        },
      ],
    }
  }, [data])

  return (
    <ReactECharts
      option={option}
      className="chart-canvas"
      opts={{ renderer: 'canvas' }}
      notMerge
      lazyUpdate
    />
  )
}
