# Static Win32 bridge. All user data arrives as JSON on stdin, never as code.
$ErrorActionPreference = 'Stop'
Add-Type -ReferencedAssemblies 'System.Web.Extensions' -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using System.Web.Script.Serialization;

public static class CheckContainment {
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
  [StructLayout(LayoutKind.Sequential)] struct Accounting {
    public long user, kernel, periodUser, periodKernel;
    public uint faults, total, active, terminated;
  }
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct Startup {
    public uint cb; public string reserved, desktop, title;
    public uint x, y, width, height, xChars, yChars, fill, flags;
    public ushort show, reservedBytes; public IntPtr reservedPointer, stdin, stdout, stderr;
  }
  [StructLayout(LayoutKind.Sequential)] struct ProcessInfo {
    public IntPtr process, thread; public uint pid, tid;
  }
  [StructLayout(LayoutKind.Sequential)] struct Security {
    public uint length; public IntPtr descriptor; [MarshalAs(UnmanagedType.Bool)] public bool inherit;
  }
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateJobObjectW(IntPtr attrs, string name);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job, int cls, ref Extended info, uint length);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job, int cls, out Accounting info, uint length, IntPtr returned);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateJobObject(IntPtr job, uint code);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateProcess(IntPtr process, uint code);
  [DllImport("kernel32.dll", SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
  [DllImport("kernel32.dll", SetLastError=true)] static extern uint WaitForSingleObject(IntPtr handle, uint ms);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr handle, out uint code);
  [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint rights, bool inherit, uint pid);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateFileW(string path, uint access, uint share, ref Security attrs, uint creation, uint flags, IntPtr template);
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcessW(string app, StringBuilder command, IntPtr processAttrs, IntPtr threadAttrs, bool inherit, uint flags, IntPtr environment, string cwd, ref Startup startup, out ProcessInfo process);
  static void Require(bool ok) { if (!ok) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()); }
  static void Close(IntPtr h) { if (h != IntPtr.Zero && h != new IntPtr(-1)) CloseHandle(h); }
  // Windows CRT argv quoting, including empty args, quotes and trailing slashes.
  static string Quote(string value) {
    var b = new StringBuilder("\""); int slashes = 0;
    foreach (char c in value) {
      if (c == '\\') { slashes++; continue; }
      if (c == '"') { b.Append('\\', slashes * 2 + 1); b.Append(c); }
      else { b.Append('\\', slashes); b.Append(c); }
      slashes = 0;
    }
    b.Append('\\', slashes * 2); b.Append('"'); return b.ToString();
  }
  static IntPtr FileHandle(string path, bool input) {
    var a = new Security { length=(uint)Marshal.SizeOf(typeof(Security)), inherit=true };
    IntPtr h = CreateFileW(path, input ? 0x80000000u : 0x40000000u, 7, ref a, 3, 0x80, IntPtr.Zero);
    Require(h != new IntPtr(-1)); return h;
  }
  static void Event(string text) { try { Console.Out.WriteLine(text); Console.Out.Flush(); } catch (IOException) {} }
  public static void MainRun(string input) {
    var json = new JavaScriptSerializer { MaxJsonLength=4194304 };
    var r = json.Deserialize<Dictionary<string,object>>(input);
    var proof = new Dictionary<string,object> {
      {"nonce",r["nonce"]}, {"state","unresolved"}, {"mechanism","windows_job"},
      {"started",false}, {"root_pid",null}, {"exit_code",null}, {"signal",null},
      {"timed_out",false}, {"owner_lost",false}, {"launch_error",null}, {"active_processes",null}
    };
    IntPtr job=IntPtr.Zero, owner=IntPtr.Zero, env=IntPtr.Zero;
    IntPtr stdin=IntPtr.Zero, stdout=IntPtr.Zero, stderr=IntPtr.Zero;
    var pi = new ProcessInfo(); bool resumed=false, assigned=false;
    try {
      owner = OpenProcess(0x100000, false, Convert.ToUInt32(r["owner_pid"])); Require(owner != IntPtr.Zero);
      if (WaitForSingleObject(owner,0) == 0) { proof["owner_lost"]=true; proof["state"]="closed"; }
      else if (File.Exists((string)r["cancel"])) { proof["state"]="closed"; } // cancelled before launch: nothing was started
      else {
        job=CreateJobObjectW(IntPtr.Zero,null); Require(job != IntPtr.Zero);
        var limits = new Extended(); limits.basic.flags=0x2000; // KILL_ON_JOB_CLOSE; no breakaway
        Require(SetInformationJobObject(job,9,ref limits,(uint)Marshal.SizeOf(typeof(Extended))));
        stdin=FileHandle("NUL",true); stdout=FileHandle((string)r["stdout"],false); stderr=FileHandle((string)r["stderr"],false);
        var si = new Startup { cb=(uint)Marshal.SizeOf(typeof(Startup)), flags=0x101, stdin=stdin, stdout=stdout, stderr=stderr };
        var command = new StringBuilder(Quote((string)r["file"]));
        foreach (object a in (System.Collections.IEnumerable)r["args"]) command.Append(" ").Append(Quote((string)a));
        var variables = new SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase);
        foreach (var entry in (Dictionary<string,object>)r["env"]) variables[entry.Key]=(string)entry.Value;
        var block = new StringBuilder(); foreach (var v in variables) block.Append(v.Key).Append('=').Append(v.Value).Append('\0'); block.Append('\0');
        env=Marshal.StringToHGlobalUni(block.ToString());
        // No user command shell. Suspension closes the launch/assignment race.
        Require(CreateProcessW((string)r["file"], command, IntPtr.Zero, IntPtr.Zero, true, 0x08000404, env, (string)r["cwd"], ref si, out pi));
        proof["root_pid"]=(long)pi.pid;
        Require(AssignProcessToJobObject(job,pi.process)); assigned=true;
        Require(ResumeThread(pi.thread) != 0xffffffff); resumed=true; proof["started"]=true;
        Event("{\"type\":\"started\",\"root_pid\":"+pi.pid+"}");
        var clock=Stopwatch.StartNew(); long cleanup=-1;
        for (;;) {
          if (WaitForSingleObject(pi.process,0)==0) { uint code; Require(GetExitCodeProcess(pi.process,out code)); proof["exit_code"]=(long)code; }
          Accounting accounting; Require(QueryInformationJobObject(job,1,out accounting,(uint)Marshal.SizeOf(typeof(Accounting)),IntPtr.Zero));
          proof["active_processes"]=(long)accounting.active;
          if (accounting.active==0) { proof["state"]="closed"; break; }
          bool lost=WaitForSingleObject(owner,0)==0;
          bool timeout=clock.Elapsed.TotalSeconds >= Convert.ToDouble(r["timeout_s"]);
          if (lost || timeout || File.Exists((string)r["cancel"])) {
            proof["owner_lost"]=lost; proof["timed_out"]=timeout;
            if (cleanup<0) { Require(TerminateJobObject(job,137)); cleanup=clock.ElapsedMilliseconds+10000; }
          }
          if (cleanup>=0 && clock.ElapsedMilliseconds>cleanup) break;
          Thread.Sleep(10);
        }
        if (resumed && WaitForSingleObject(pi.process,0)==0) { uint code; Require(GetExitCodeProcess(pi.process,out code)); proof["exit_code"]=(long)code; }
      }
    } catch (Exception failure) {
      var native = failure as System.ComponentModel.Win32Exception;
      proof["launch_error"]="NATIVE_CONTAINMENT_FAILED:"+failure.GetType().Name+(native==null ? "" : ":"+native.NativeErrorCode);
      if (job != IntPtr.Zero) TerminateJobObject(job,137);
      if (pi.process != IntPtr.Zero && !assigned) TerminateProcess(pi.process,137);
      bool rootStopped=pi.process==IntPtr.Zero || WaitForSingleObject(pi.process,10000)==0;
      Accounting accounting;
      bool treeStopped=job==IntPtr.Zero || (QueryInformationJobObject(job,1,out accounting,(uint)Marshal.SizeOf(typeof(Accounting)),IntPtr.Zero) && accounting.active==0);
      if (rootStopped && treeStopped) { proof["state"]="closed"; proof["active_processes"]=0; }
    } finally {
      Close(pi.thread); Close(pi.process); Close(stdin); Close(stdout); Close(stderr); Close(owner); Close(job);
      if (env != IntPtr.Zero) Marshal.FreeHGlobal(env);
    }
    // Exclusive, UTF-8 proof survives supervisor loss. Never infer this from a
    // direct-child exit or from taskkill's return code.
    using (var f=new FileStream((string)r["proof"],FileMode.CreateNew,FileAccess.Write,FileShare.Read))
    using (var w=new StreamWriter(f,new UTF8Encoding(false))) w.WriteLine(json.Serialize(proof));
    Event("{\"type\":\"finished\"}");
  }
}
'@
$requestReader = [System.IO.StreamReader]::new([Console]::OpenStandardInput(), [System.Text.UTF8Encoding]::new($false), $true)
try { [CheckContainment]::MainRun($requestReader.ReadToEnd()) }
finally { $requestReader.Dispose() }
