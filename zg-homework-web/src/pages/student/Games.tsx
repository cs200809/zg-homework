/** 学生端游戏中心：数独 + 成语接龙（PRD 5.6、9 学生端）。 */

import { useEffect, useRef, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Progress,
  Result,
  Row,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { TrophyOutlined } from '@ant-design/icons'

import { gamesApi } from '../../api/student'
import type { GameRecord, IdiomQuestionView } from '../../api/types'

const DIFFICULTY_LABEL: Record<string, string> = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
}

// ---------------- 数独 ----------------

function SudokuPanel() {
  const { message } = App.useApp()
  const [puzzle, setPuzzle] = useState<{
    puzzle_id: string
    board: number[][]
    difficulty: string
  } | null>(null)
  const [cells, setCells] = useState<number[][]>([])
  const [selected, setSelected] = useState<[number, number] | null>(null)
  const [startedAt, setStartedAt] = useState(0)

  async function start(difficulty: 'easy' | 'medium' | 'hard') {
    try {
      const r = await gamesApi.sudokuStart(difficulty)
      setPuzzle(r)
      setCells(r.board.map((row) => row.map((v) => (v === 0 ? 0 : v))))
      setStartedAt(Date.now())
      setSelected(null)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '生成题目失败')
    }
  }

  function input(v: number) {
    if (!selected || !puzzle) return
    const [r, c] = selected
    if (puzzle.board[r][c] !== 0) return // 提示数不可改
    const next = cells.map((row) => row.slice())
    next[r][c] = v
    setCells(next)
  }

  async function submit(success: boolean) {
    if (!puzzle) return
    const duration = Math.floor((Date.now() - startedAt) / 1000)
    try {
      const r = await gamesApi.sudokuResult(puzzle.puzzle_id, duration, success, cells)
      if (r.success) {
        message.success(`完成！获得 ${r.points} 积分`)
      } else {
        message.warning(r.points > 0 ? `通过，得 ${r.points} 分` : '未完成或答案有误')
      }
      setPuzzle(null)
      setCells([])
    } catch (e) {
      message.error(e instanceof Error ? e.message : '提交失败')
    }
  }

  return (
    <div>
      {!puzzle ? (
        <Card>
          <Typography.Paragraph type="secondary">
            选择难度开始数独。服务端按难度实时生成题目，保证唯一解。
          </Typography.Paragraph>
          <Space>
            <Button type="primary" onClick={() => start('easy')}>
              简单（+5）
            </Button>
            <Button onClick={() => start('medium')}>中等（+10）</Button>
            <Button onClick={() => start('hard')}>困难（+15）</Button>
          </Space>
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
            message="数独与成语接龙共用「每日游戏合计 20 分」上限"
          />
        </Card>
      ) : (
        <Card
          title={`数独 · ${DIFFICULTY_LABEL[puzzle.difficulty]}`}
          extra={
            <Space>
              <Button onClick={() => setPuzzle(null)}>放弃</Button>
              <Button onClick={() => submit(false)}>未完成</Button>
              <Button type="primary" onClick={() => submit(true)}>
                提交答案
              </Button>
            </Space>
          }
        >
          <div style={{ display: 'inline-block' }}>
            {cells.map((row, r) => (
              <div key={r} style={{ display: 'flex' }}>
                {row.map((v, c) => {
                  const isGiven = puzzle.board[r][c] !== 0
                  const active = selected?.[0] === r && selected?.[1] === c
                  const borderRight = c % 3 === 2 && c !== 8 ? '2px solid #000' : '1px solid #d9d9d9'
                  const borderBottom = r % 3 === 2 && r !== 8 ? '2px solid #000' : '1px solid #d9d9d9'
                  return (
                    <div
                      key={c}
                      onClick={() => {
                        if (!isGiven) setSelected([r, c])
                      }}
                      style={{
                        width: 40,
                        height: 40,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        borderRight,
                        borderBottom,
                        background: active ? '#e6f4ff' : isGiven ? '#fafafa' : '#fff',
                        fontWeight: isGiven ? 700 : 400,
                        fontSize: 18,
                        cursor: isGiven ? 'default' : 'pointer',
                        userSelect: 'none',
                      }}
                    >
                      {v === 0 ? '' : v}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>

          <div style={{ marginTop: 16 }}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
              <Button key={n} style={{ marginRight: 8 }} onClick={() => input(n)}>
                {n}
              </Button>
            ))}
            <Button style={{ marginLeft: 8 }} onClick={() => input(0)}>
              清除
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}

// ---------------- 成语接龙 ----------------

function IdiomPanel() {
  const { message } = App.useApp()
  const [sessionId, setSessionId] = useState('')
  const [question, setQuestion] = useState<IdiomQuestionView | null>(null)
  const [correct, setCorrect] = useState(0)
  const [wrong, setWrong] = useState(0)
  const [remaining, setRemaining] = useState(60)
  const [finished, setFinished] = useState(false)
  const [gained, setGained] = useState<number | null>(null)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
    }
  }, [])

  async function start() {
    try {
      const r = await gamesApi.idiomStart()
      setSessionId(r.session_id)
      setCorrect(0)
      setWrong(0)
      setRemaining(r.duration_seconds)
      setFinished(false)
      setGained(null)
      if (timerRef.current) window.clearInterval(timerRef.current)
      timerRef.current = window.setInterval(() => {
        setRemaining((v) => {
          if (v <= 1) {
            if (timerRef.current) window.clearInterval(timerRef.current)
            return 0
          }
          return v - 1
        })
      }, 1000)
      await nextQuestion(r.session_id)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '无法开始游戏')
    }
  }

  async function nextQuestion(sid = sessionId) {
    try {
      const r = await gamesApi.idiomQuestion(sid)
      setQuestion(r.question)
      setRemaining(r.remaining_seconds)
    } catch (e) {
      message.warning(e instanceof Error ? e.message : '无法获取题目')
    }
  }

  async function answer(value: string) {
    try {
      const r = await gamesApi.idiomAnswer(sessionId, value)
      setCorrect(r.correct_count)
      setWrong(r.wrong_count)
      setRemaining(r.remaining_seconds)
      if (r.correct) {
        message.success('答对了！')
      } else {
        message.error(`答错了，正确答案是「${r.right_answer}」`)
      }
      await nextQuestion()
    } catch (e) {
      message.warning(e instanceof Error ? e.message : '无法提交')
      await finish()
    }
  }

  async function finish() {
    try {
      const r = await gamesApi.idiomResult(sessionId)
      setGained(r.points)
      setFinished(true)
      setQuestion(null)
      if (timerRef.current) window.clearInterval(timerRef.current)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '提交结果失败')
    }
  }

  if (finished) {
    return (
      <Card>
        <Result
          status="success"
          title="闯关结束"
          subTitle={`答对 ${correct} 题，答错 ${wrong} 题`}
          extra={
            <Statistic
              title="获得积分"
              value={gained ?? 0}
              suffix="分"
              prefix={<TrophyOutlined />}
            />
          }
        >
          <Button type="primary" onClick={start}>
            再来一局
          </Button>
        </Result>
      </Card>
    )
  }

  if (!sessionId) {
    return (
      <Card>
        <Typography.Paragraph type="secondary">
          60 秒限时闯关，答对一题得 1 分。题目由老师/管理员在后台导入。
        </Typography.Paragraph>
        <Button type="primary" onClick={start}>
          开始闯关
        </Button>
      </Card>
    )
  }

  return (
    <Card
      title="成语接龙"
      extra={
        <Space>
          <Tag color={remaining <= 10 ? 'red' : 'blue'}>剩余 {remaining}s</Tag>
          <Tag color="green">答对 {correct}</Tag>
          <Tag color="red">答错 {wrong}</Tag>
          <Button size="small" onClick={finish}>
            结束
          </Button>
        </Space>
      }
    >
      <Progress
        percent={Math.round(((60 - remaining) / 60) * 100)}
        status={remaining <= 10 ? 'exception' : 'active'}
      />

      {question && (
        <div style={{ textAlign: 'center', marginTop: 24 }}>
          <Typography.Title level={3}>{question.prompt}</Typography.Title>
          <Row gutter={[12, 12]} justify="center" style={{ marginTop: 16 }}>
            {question.options.map((opt) => (
              <Col key={opt} xs={12} sm={8}>
                <Button block size="large" onClick={() => answer(opt)}>
                  {opt}
                </Button>
              </Col>
            ))}
          </Row>
        </div>
      )}
    </Card>
  )
}

// ---------------- 游戏记录 ----------------

function RecordsPanel() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<GameRecord[]>([])

  useEffect(() => {
    ;(async () => {
      try {
        const r = await gamesApi.records(1, 20)
        setRows(r.list)
      } catch (e) {
        message.error(e instanceof Error ? e.message : '加载失败')
      }
    })()
  }, [message])

  return (
    <Table<GameRecord>
      rowKey="id"
      dataSource={rows}
      pagination={false}
      locale={{ emptyText: '还没有游戏记录' }}
      columns={[
        {
          title: '游戏',
          dataIndex: 'game_type',
          render: (v: string) => (v === 'sudoku' ? '数独' : '成语接龙'),
        },
        {
          title: '难度',
          dataIndex: 'difficulty',
          render: (v: string | null) => (v ? DIFFICULTY_LABEL[v] ?? v : '-'),
        },
        { title: '得分', dataIndex: 'points' },
        { title: '时长(秒)', dataIndex: 'duration_seconds' },
        {
          title: '时间',
          dataIndex: 'created_at',
          render: (v: string | null) => (v ? new Date(v).toLocaleString() : '-'),
        },
      ]}
    />
  )
}

export default function StudentGames() {
  return (
    <Tabs
      items={[
        { key: 'sudoku', label: '数独', children: <SudokuPanel /> },
        { key: 'idiom', label: '成语接龙', children: <IdiomPanel /> },
        { key: 'records', label: '游戏记录', children: <RecordsPanel /> },
      ]}
    />
  )
}