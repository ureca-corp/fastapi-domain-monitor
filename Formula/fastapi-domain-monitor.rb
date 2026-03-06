# Homebrew formula for fastapi-domain-monitor
#
# ── 배포 방법 ─────────────────────────────────────────────────────────────
#  1. homebrew-tap GitHub 레포 생성:  github.com/YOUR_USERNAME/homebrew-tap
#  2. 이 파일을 Formula/fastapi-domain-monitor.rb 로 복사
#  3. YOUR_USERNAME 을 실제 GitHub 유저명으로 교체
#
# ── 설치 방법 ─────────────────────────────────────────────────────────────
#  brew tap YOUR_USERNAME/tap
#  brew install fastapi-domain-monitor
#
# ── 사용 방법 ─────────────────────────────────────────────────────────────
#  cd your-fastapi-project
#  domain-monitor start                       # src/modules 자동 감지
#  domain-monitor start --watch src/modules   # 경로 지정
#  domain-monitor start --port 9000           # 포트 변경
# ──────────────────────────────────────────────────────────────────────────

class FastapiDomainMonitor < Formula
  desc "Real-time SQLModel domain diagram dashboard for FastAPI projects"
  homepage "https://github.com/YOUR_USERNAME/claude-code-agent-monitor-dashboard"

  # GitHub 릴리즈 태그를 만들면 url/sha256 방식 사용 (재현 가능 빌드):
  #   url "https://github.com/YOUR_USERNAME/repo/archive/refs/tags/v0.1.0.tar.gz"
  #   sha256 "$(curl -sL <url> | shasum -a 256 | cut -d' ' -f1)"
  #
  # HEAD(최신 main)로 설치:
  url "https://github.com/YOUR_USERNAME/claude-code-agent-monitor-dashboard.git",
      using: :git,
      branch: "main"
  version "0.1.0"

  license "MIT"
  head "https://github.com/YOUR_USERNAME/claude-code-agent-monitor-dashboard.git", branch: "main"

  depends_on "python@3.12"

  def install
    # Homebrew sandbox 환경에서 pip로 의존성 포함 설치
    python3 = Formula["python@3.12"].opt_bin/"python3.12"
    venv = virtualenv_create(libexec, python3)

    # pip install . 실행 (click, uvicorn, watchdog, fastapi 등 자동 설치)
    venv.pip_install(buildpath)

    # domain-monitor 바이너리를 PATH에 연결
    bin.install_symlink libexec/"bin/domain-monitor"
  end

  def post_install
    ohai "domain-monitor installed!"
    ohai "Usage: cd your-project && domain-monitor start"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/domain-monitor --version")
    assert_match "start", shell_output("#{bin}/domain-monitor --help")
  end
end
