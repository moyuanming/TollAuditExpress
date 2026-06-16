// 饼图:检测类型分布
import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'

const COLORS = ['#5180FF', '#22A06B', '#D8992A', '#D84C57']
const TEXT_PRIMARY = '#191C1E'
const TEXT_SECONDARY = '#667085'
const BORDER = 'rgba(25,28,30,0.12)'

export default function PieDistribution({ data = [] }) {
  const option = useMemo(() => ({
    color: COLORS,
    tooltip: {
      trigger: 'item',
      backgroundColor: '#FFFFFF',
      borderColor: BORDER,
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: TEXT_PRIMARY, fontFamily: 'Inter, "PingFang SC", sans-serif', fontSize: 12 },
      extraCssText: 'box-shadow: 0 14px 40px -12px rgba(25,28,30,0.10); border-radius: 14px;',
    },
    legend: {
      orient: 'vertical',
      right: 8,
      top: 'middle',
      textStyle: { color: TEXT_SECONDARY, fontFamily: 'Inter, "PingFang SC", sans-serif', fontSize: 12 },
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 12,
    },
    series: [
      {
        name: '检测分布',
        type: 'pie',
        radius: ['52%', '78%'],
        center: ['38%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 6, borderColor: '#FFFFFF', borderWidth: 3 },
        label: { show: false },
        labelLine: { show: false },
        data: data.map((d, i) => ({
          name: d.name,
          value: d.value,
          itemStyle: { color: COLORS[i % COLORS.length] },
        })),
      },
    ],
  }), [data])

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
