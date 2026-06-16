// 折线图:近 30 天每日检测 / 可疑 / 确认欺诈趋势
import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'

const PRIMARY = '#5180FF'
const SUCCESS = '#22A06B'
const DANGER = '#D84C57'
const TEXT_PRIMARY = '#191C1E'
const TEXT_SECONDARY = '#667085'
const BORDER = 'rgba(25,28,30,0.12)'

export default function LineTrend({ data = [] }) {
  const option = useMemo(() => {
    const labels = data.map(d => d.date.slice(5)) // MM-DD
    return {
      grid: { top: 36, right: 24, bottom: 32, left: 48, containLabel: true },
      legend: {
        top: 4,
        right: 0,
        textStyle: { color: TEXT_SECONDARY, fontFamily: 'Inter, "PingFang SC", sans-serif', fontSize: 12 },
        icon: 'roundRect',
        itemWidth: 10,
        itemHeight: 10,
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#FFFFFF',
        borderColor: BORDER,
        borderWidth: 1,
        padding: [10, 14],
        textStyle: { color: TEXT_PRIMARY, fontFamily: 'Inter, "PingFang SC", sans-serif', fontSize: 12 },
        extraCssText: 'box-shadow: 0 14px 40px -12px rgba(25,28,30,0.10); border-radius: 14px;',
      },
      xAxis: {
        type: 'category',
        data: labels,
        boundaryGap: false,
        axisLine: { lineStyle: { color: BORDER } },
        axisTick: { show: false },
        axisLabel: { color: TEXT_SECONDARY, fontFamily: 'Inter, "PingFang SC", sans-serif', fontSize: 11 },
      },
      yAxis: {
        type: 'value',
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: TEXT_SECONDARY, fontFamily: 'Inter, "PingFang SC", sans-serif', fontSize: 11 },
      },
      series: [
        {
          name: '总检测',
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { width: 2.5, color: PRIMARY },
          itemStyle: { color: PRIMARY, borderColor: '#FFFFFF', borderWidth: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(81,128,255,0.18)' },
                { offset: 1, color: 'rgba(81,128,255,0.00)' },
              ],
            },
          },
          data: data.map(d => d.detected),
        },
        {
          name: '可疑',
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { width: 2.5, color: DANGER },
          itemStyle: { color: DANGER, borderColor: '#FFFFFF', borderWidth: 2 },
          data: data.map(d => d.suspected),
        },
        {
          name: '确认欺诈',
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { width: 2.5, color: SUCCESS },
          itemStyle: { color: SUCCESS, borderColor: '#FFFFFF', borderWidth: 2 },
          data: data.map(d => d.confirmed),
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
