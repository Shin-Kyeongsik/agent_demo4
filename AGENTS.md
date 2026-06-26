# Agent Usage Guide

## 법인카드 분석 요청 안내

이 프로젝트에서 법인카드 사용 내역 분석이 필요한 경우에는 `skills/analyze-corporate-cards` Skill을 사용하세요.

### 추천 호출 방식

```text
$analyze-corporate-cards를 사용해서 2026년 5월 법인카드 거래를 분석해줘.
```

```text
$analyze-corporate-cards를 사용해서 검토가 필요한 법인카드 거래를 찾아줘.
```

### 사용 목적별 예시

- 월별 지출 요약
- 부서별/직원별 사용 현황
- 중복 결제 의심 거래 탐지
- 분할 결제 의심 거래 탐지
- 고액 거래 및 주말 사용 거래 검토
- 메모 누락 거래 확인
- 거래처 명칭 통합 검토

### 주의 사항

- `AGENTS.md`나 다른 안내 문서에서 법인카드 분석 요청을 할 때는 `skills/analyze-corporate-cards` Skill 명칭을 명시하면 검색 및 호출에 도움이 됩니다.
- 가능한 한 `"$analyze-corporate-cards"`를 포함한 구체적인 요청 문장을 사용하세요.
