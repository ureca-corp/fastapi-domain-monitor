class FastapiDomainMonitor < Formula
  desc "Real-time SQLModel domain diagram dashboard for FastAPI projects"
  homepage "https://github.com/ureca-corp/fastapi-domain-monitor"
  url "https://github.com/ureca-corp/fastapi-domain-monitor/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "dea3896aa0851e303c0df2e0828f945ee48065038a47548139d767e4311605fa"
  license "MIT"

  depends_on "python@3.12"

  def install
    python3 = Formula["python@3.12"].opt_bin/"python3.12"

    # Homebrew의 venv.pip_install()은 --no-deps를 붙이므로 직접 호출
    system python3, "-m", "venv", libexec
    system libexec/"bin/pip", "install", "--no-cache-dir", buildpath.to_s

    bin.install_symlink libexec/"bin/domain-monitor"
  end

  test do
    assert_match "0.1.0", shell_output("#{bin}/domain-monitor --version")
    assert_match "start", shell_output("#{bin}/domain-monitor --help")
  end
end
