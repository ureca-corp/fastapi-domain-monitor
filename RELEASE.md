# Release Guide — fastapi-domain-monitor

> 에이전트/자동화 전용 배포 절차 문서.
> 이 파일은 Claude Code 등 AI 에이전트가 배포 작업을 수행할 때 참조한다.

---

## 1. 저장소 구조

| 저장소 | 역할 | URL |
|--------|------|-----|
| `ureca-corp/fastapi-domain-monitor` | 패키지 소스 코드 | https://github.com/ureca-corp/fastapi-domain-monitor |
| PyPI | Python 패키지 배포 | https://pypi.org/project/fastapi-domain-monitor |

로컬 소스 루트: `/Users/andy/Documents/GitHub/claude-code-agent-monitor-dashboard`

---

## 2. 버전 규칙 (Semantic Versioning)

```
MAJOR.MINOR.PATCH
  │     │     └── 버그 수정, warning 제거, 문서 수정
  │     └──────── 하위 호환 기능 추가
  └────────────── 하위 비호환 변경 (API 변경, 삭제)
```

**현재 버전**: `0.1.4`

버전 소스는 `pyproject.toml` 단일 파일:
```toml
[project]
version = "0.1.4"
```

`src/fastapi_domain_monitor/__init__.py`의 `__version__`도 함께 수정:
```python
__version__ = "0.1.4"
```

---

## 3. 배포 전 체크리스트

```
[ ] pytest tests/ -v → 전체 통과 확인 (warnings 0개 포함)
[ ] pyproject.toml version 업데이트
[ ] __init__.py __version__ 업데이트
[ ] 변경사항 커밋 (아래 커밋 컨벤션 참조)
```

---

## 4. 전체 배포 절차 (단계별)

### Step 1 — 테스트 통과 확인

```bash
cd /Users/andy/Documents/GitHub/claude-code-agent-monitor-dashboard
python -m pytest tests/ -v
```

실패하면 배포 중단. warnings도 0개여야 한다.

### Step 2 — 버전 업데이트

```toml
# pyproject.toml
version = "0.1.X"  # 새 버전으로 수정
```

```python
# src/fastapi_domain_monitor/__init__.py
__version__ = "0.1.X"
```

### Step 3 — 커밋 & 소스 저장소 푸시

커밋 메시지 컨벤션:
```
feat: vX.Y.Z - <한 줄 요약>

- 변경 항목 1
- 변경 항목 2

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

```bash
git add pyproject.toml src/ tests/
git commit -m "feat: vX.Y.Z - ..."
git push origin main
```

### Step 4 — Git 태그 생성 및 푸시

태그 형식: `v{MAJOR}.{MINOR}.{PATCH}` (반드시 `v` 접두사 포함)

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

### Step 5 — PyPI 배포

```bash
rm -rf dist/
uv build
uv publish
```

`uv`가 없으면: `pip3 install build && python3 -m build && python3 -m twine upload dist/*`

---

## 5. 사용자 설치 방법

```bash
pip install fastapi-domain-monitor==X.Y.Z
```

---

## 6. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `uv publish` 인증 오류 | PyPI token 만료 | `uv publish --token <token>` 또는 `.pypirc` 확인 |
| `git push` 태그 실패 | 태그가 이미 존재 | `git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z` 후 재생성 |

---

## 7. 배포 체크리스트 요약 (빠른 참조)

```
[ ] pytest 전체 통과 (warnings 0)
[ ] pyproject.toml version 수정
[ ] __init__.py __version__ 수정
[ ] git commit → git push origin main
[ ] git tag vX.Y.Z → git push origin vX.Y.Z
[ ] uv build → uv publish  (PyPI)
```
