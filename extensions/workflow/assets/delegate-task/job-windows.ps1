# Puts one process (the delegate supervisor) in a new kill-on-close job object
# and leaves the ONLY handle to that job inside the process itself. When that
# process exits for any reason, including a hard kill, Windows closes the job
# and terminates every process still in it: the harness and all its
# descendants. Prints "windows_job" on success; any failure exits non-zero.
param([Parameter(Mandatory=$true)][ValidateRange(1, [int]::MaxValue)][int]$TargetPid)
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class SupervisorJob {
  [StructLayout(LayoutKind.Sequential)] struct Limits {
    public long perProcess, perJob; public uint flags;
    public UIntPtr minWorking, maxWorking; public uint activeLimit;
    public UIntPtr affinity; public uint priority, scheduling;
  }
  [StructLayout(LayoutKind.Sequential)] struct Io {
    public ulong readOps, writeOps, otherOps, readBytes, writeBytes, otherBytes;
  }
  [StructLayout(LayoutKind.Sequential)] struct Extended {
    public Limits basic; public Io io;
    public UIntPtr processMemory, jobMemory, peakProcessMemory, peakJobMemory;
  }
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateJobObjectW(IntPtr attrs, string name);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job, int cls, ref Extended info, uint length);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
  [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint rights, bool inherit, uint pid);
  [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr GetCurrentProcess();
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool DuplicateHandle(IntPtr srcProcess, IntPtr src, IntPtr dstProcess, out IntPtr dst, uint access, bool inherit, uint options);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
  static void Require(bool ok) { if (!ok) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()); }

  public static void Contain(uint pid) {
    IntPtr job = IntPtr.Zero, target = IntPtr.Zero;
    try {
      job = CreateJobObjectW(IntPtr.Zero, null); Require(job != IntPtr.Zero);
      var limits = new Extended(); limits.basic.flags = 0x2000; // KILL_ON_JOB_CLOSE; no breakaway
      Require(SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf(typeof(Extended))));
      // SET_QUOTA | TERMINATE (assignment) and DUP_HANDLE (handle hand-over).
      target = OpenProcess(0x0100 | 0x0001 | 0x0040, false, pid); Require(target != IntPtr.Zero);
      // Hand the handle over BEFORE assigning: if this helper died between the
      // two steps with only its own handle open, closing it would kill the target.
      IntPtr remote;
      Require(DuplicateHandle(GetCurrentProcess(), job, target, out remote, 0, false, 2)); // DUPLICATE_SAME_ACCESS
      Require(AssignProcessToJobObject(job, target));
    } finally {
      if (target != IntPtr.Zero) CloseHandle(target);
      if (job != IntPtr.Zero) CloseHandle(job); // the target now holds the only handle
    }
  }
}
'@
[SupervisorJob]::Contain([uint32]$TargetPid)
'windows_job'
