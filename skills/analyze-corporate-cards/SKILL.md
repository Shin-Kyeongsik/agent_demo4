---
name: analyze-corporate-cards
description: 법인카드/corporate card 거래 스프레드시트를 작업별 Python entrypoint로 분석한다. Codex가 .xlsx, .xls, .csv, .tsv 형식의 법인카드 사용내역, 특히 data/ 아래 파일을 바탕으로 부서별 총액/건수/평균, 지출 요약, 중복 결제 후보, 분할 결제 후보, 고액 거래, 주말 사용, 메모 누락, 재승인 메모, 거래처 표기 통합, 감사용 종합 리포트를 답해야 할 때 사용한다.
---

# Analyze Corporate Cards

## 개요

사용자 질문에 답하는 데 필요한 가장 작은 작업별 스크립트를 실행하고, 스크립트가 stdout으로 출력한 계산 결과를 읽어 사용자에게 답한다.

기본 동작은 결과 파일을 `outputs/`에 저장하지 않는 것이다. 원본 파일 처리를 위한 중간 파일은 임시 디렉터리에 만들고 실행 후 버린다. 사용자가 산출물 파일을 명시적으로 요청할 때만 `--out <dir>`을 추가한다.

## 요청별 실행 경로

### 부서별 총액, 건수, 평균

다음과 같은 질문에는 이 경로를 사용한다: "부서별 총액/건수/평균을 알려줘", "어느 부서가 가장 많이 썼어?", "부서별 사용 현황만 요약해줘".

```bash
python3 <skill-dir>/scripts/summarize_departments.py --input data
```

명령 stdout에 Markdown 요약이 출력된다. 그 표와 범위 정보를 근거로 바로 답한다.

### 검토가 필요한 거래

다음과 같은 질문에는 이 경로를 사용한다: "검토가 필요한 거래 알려줘", "이상 거래 찾아줘", "중복 결제 의심 건만 봐줘", "감사 대상 거래를 뽑아줘".

```bash
python3 <skill-dir>/scripts/find_review_transactions.py --input data
```

명령 stdout에 검토 후보 유형별 요약, 상위 후보, 거래ID, 원본 행 번호가 출력된다. 중요한 예시는 `finding_id`, `Tx IDs`, `Source Rows`를 함께 언급한다.

### 종합 분석 리포트

사용자가 "전체 분석", "리포트", "종합 감사", "월별 파일 전체를 분석"을 요청하거나, 지출 요약과 검토 후보를 함께 요구할 때만 사용한다.

```bash
python3 <skill-dir>/scripts/run_pipeline.py --input data
```

명령 stdout에 종합 Markdown 리포트가 출력된다. 이 리포트를 기준으로 답한다.

### 입력 파일 점검 또는 스키마 확인

사용자가 어떤 파일, 시트, 컬럼, 행 수가 있는지 묻거나 컬럼 매핑을 확인하려 할 때 사용한다.

```bash
python3 <skill-dir>/scripts/inspect_input.py --input data
```

명령 stdout에 JSON 프로필이 출력된다. 필요한 파일명, 시트명, 컬럼명, 행 수만 요약해 답한다.

### 정규화 파일이 필요한 경우

후속 분석을 여러 번 반복하거나, 사용자가 정규화된 거래 파일 자체를 요청할 때만 파일 저장형 정규화를 실행한다.

```bash
python3 <skill-dir>/scripts/normalize_transactions.py --input data --out outputs/corporate-card-normalized
```

이 경로는 예외적으로 파일을 만든다. 단순 질문 답변에는 사용하지 않는다.

## 공통 옵션

- 통합문서에 여러 시트가 있고 사용자가 특정 시트를 지정하면 `--sheet <sheet-name>`을 추가한다.
- 준비된 정규화 파일을 재사용하려면 `--transactions <path/to/normalized_transactions.csv>`를 추가한다.
- 기간을 제한한 부서별 요약이 필요하면 `summarize_departments.py`에 `--from-date YYYY-MM-DD --to-date YYYY-MM-DD`를 추가한다.
- 고액 거래 검토 기준을 조정하려면 `--high-amount <KRW>`를 추가한다.
- 분할 결제 후보 기준을 조정하려면 `find_review_transactions.py`에 `--split-min-total <KRW>`를 추가한다.
- 내부 처리 로그가 필요할 때만 `--verbose`를 추가한다.
- 사용자가 파일 산출물을 명시적으로 요청할 때만 `--out <dir>`을 추가한다.

## 답변 원칙

- 스크립트 stdout의 최종 Markdown 또는 JSON만 읽고 답한다.
- 부서별 요약 요청은 `summarize_departments.py` stdout을 기준으로 답한다.
- 검토 거래 요청은 `find_review_transactions.py` stdout을 기준으로 답한다.
- 종합 리포트 요청은 `run_pipeline.py` stdout을 기준으로 답한다.
- 스크립트가 탐지한 항목은 확정된 위반이 아니라 검토 후보로 표현한다.
- 사용자가 원본 행 단위 근거를 요청하면 stdout에 포함된 거래ID와 원본 행 번호를 우선 사용한다.
- 원본 거래 전체를 컨텍스트에 올리지 않는다.

## 스크립트

- `inspect_input.py`: 파일, 시트, 컬럼, 행 수, 결측치 수, 미리보기 정보를 stdout JSON으로 출력한다.
- `normalize_transactions.py`: 원본 컬럼을 공통 거래 스키마로 매핑하고 파일로 저장한다.
- `summarize_departments.py`: 부서별 총액, 건수, 평균, 통제 신호를 stdout Markdown 또는 JSON으로 출력한다.
- `find_review_transactions.py`: 검토 후보 탐지와 점수화를 실행하고 stdout Markdown 또는 JSON으로 출력한다.
- `summarize_usage.py`: 종합 리포트용 전체 집계 테이블을 만든다.
- `detect_findings.py`: 원시 검토 후보를 생성한다.
- `score_findings.py`: 검토 후보에 점수를 매기고 정렬한다.
- `render_report.py`: 종합 Markdown 리포트를 생성한다.
- `run_pipeline.py`: 넓은 범위의 분석을 실행하고 최종 리포트를 stdout으로 출력한다.

탐지 규칙을 설명하거나 기준값을 조정해야 할 때만 `references/policy_rules.md`를 읽는다.
