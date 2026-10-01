using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

internal static class BuildIdentity
{
    internal const string ProductName = "AAVDS-duct-builder";
    internal const string ProductVersion = "AAVDS-2026-V01";
    internal const bool Signed = false;
}

internal static class EmbeddedPackage
{
    private const string PayloadMarker = "AAVDS_PAYLOAD_V1";
    private const int FooterSearchBytes = 4 * 1024 * 1024;

    internal static PackageArchive Open()
    {
        FileStream executable = File.Open(
            Application.ExecutablePath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read);
        try
        {
            long payloadLength;
            long footerPosition = FindPayloadFooter(executable, out payloadLength);
            SegmentStream payload = new SegmentStream(
                executable,
                footerPosition - payloadLength,
                payloadLength,
                false);
            return new PackageArchive(payload, new ZipArchive(payload, ZipArchiveMode.Read, false));
        }
        catch
        {
            executable.Dispose();
            throw;
        }
    }

    internal static void Verify(ZipArchive archive)
    {
        AssertEntry(archive, "app/Allshield_Project_GUI.py");
        AssertEntry(archive, "app/MANIFEST.json");
        AssertEntry(archive, "FreeCAD/bin/python.exe");
        AssertEntry(archive, "FreeCAD/bin/pythonw.exe");
        AssertEntry(archive, "FreeCAD/bin/freecad.exe");
        AssertEntry(archive, "Uninstall-AAVDS.ps1");
    }

    private static void AssertEntry(ZipArchive archive, string path)
    {
        if (archive.GetEntry(path) == null)
        {
            throw new InvalidDataException("Missing package file: " + path);
        }
    }

    private static long FindPayloadFooter(Stream executable, out long payloadLength)
    {
        byte[] marker = Encoding.ASCII.GetBytes(PayloadMarker);
        long searchStart = Math.Max(0, executable.Length - FooterSearchBytes);
        int searchLength = checked((int)(executable.Length - searchStart));
        byte[] tail = new byte[searchLength];
        executable.Position = searchStart;
        ReadExactly(executable, tail, 0, tail.Length);

        for (int index = tail.Length - marker.Length - sizeof(long); index >= 0; index--)
        {
            if (!MatchesAt(tail, index, marker))
            {
                continue;
            }

            long candidateLength = BitConverter.ToInt64(tail, index + marker.Length);
            long footerPosition = searchStart + index;
            long candidateStart = footerPosition - candidateLength;
            if (candidateLength <= 0 || candidateStart < 0)
            {
                continue;
            }

            executable.Position = candidateStart;
            if (executable.ReadByte() == 'P' && executable.ReadByte() == 'K')
            {
                payloadLength = candidateLength;
                return footerPosition;
            }
        }

        throw new InvalidDataException("Embedded installer payload not found.");
    }

    private static bool MatchesAt(byte[] source, int index, byte[] value)
    {
        for (int offset = 0; offset < value.Length; offset++)
        {
            if (source[index + offset] != value[offset])
            {
                return false;
            }
        }
        return true;
    }

    private static void ReadExactly(Stream stream, byte[] buffer, int offset, int count)
    {
        while (count > 0)
        {
            int read = stream.Read(buffer, offset, count);
            if (read == 0)
            {
                throw new EndOfStreamException();
            }
            offset += read;
            count -= read;
        }
    }

    internal sealed class PackageArchive : IDisposable
    {
        private readonly Stream payload;

        internal PackageArchive(Stream payload, ZipArchive archive)
        {
            this.payload = payload;
            Archive = archive;
        }

        internal ZipArchive Archive { get; private set; }

        public void Dispose()
        {
            Archive.Dispose();
            payload.Dispose();
        }
    }

    private sealed class SegmentStream : Stream
    {
        private readonly Stream inner;
        private readonly long offset;
        private readonly long length;
        private readonly bool leaveOpen;
        private long position;

        internal SegmentStream(Stream inner, long offset, long length, bool leaveOpen)
        {
            this.inner = inner;
            this.offset = offset;
            this.length = length;
            this.leaveOpen = leaveOpen;
        }

        public override bool CanRead { get { return true; } }
        public override bool CanSeek { get { return true; } }
        public override bool CanWrite { get { return false; } }
        public override long Length { get { return length; } }
        public override long Position
        {
            get { return position; }
            set { Seek(value, SeekOrigin.Begin); }
        }

        public override int Read(byte[] buffer, int bufferOffset, int count)
        {
            if (position >= length)
            {
                return 0;
            }
            int allowed = (int)Math.Min(count, length - position);
            inner.Position = offset + position;
            int read = inner.Read(buffer, bufferOffset, allowed);
            position += read;
            return read;
        }

        public override long Seek(long seekOffset, SeekOrigin origin)
        {
            long target = origin == SeekOrigin.Begin
                ? seekOffset
                : origin == SeekOrigin.Current
                    ? position + seekOffset
                    : length + seekOffset;
            if (target < 0 || target > length)
            {
                throw new IOException("Attempted to seek outside the embedded payload.");
            }
            position = target;
            return position;
        }

        public override void Flush() { }
        public override void SetLength(long value) { throw new NotSupportedException(); }
        public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }

        protected override void Dispose(bool disposing)
        {
            if (disposing && !leaveOpen)
            {
                inner.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}

internal sealed class InstallerForm : Form
{
    private readonly Label statusLabel;
    private readonly ProgressBar progressBar;
    private readonly CheckBox desktopShortcut;
    private readonly Button installButton;
    private readonly Button cancelButton;
    private readonly BackgroundWorker worker;
    private bool installationStarted;

    internal InstallerForm()
    {
        ExitCode = 2;
        Text = BuildIdentity.ProductName + " Setup";
        ClientSize = new Size(570, 300);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9F, FontStyle.Regular, GraphicsUnit.Point);
        BackColor = Color.White;

        Label heading = new Label();
        heading.Location = new Point(28, 24);
        heading.Size = new Size(514, 34);
        heading.Font = new Font("Segoe UI Semibold", 16F, FontStyle.Bold, GraphicsUnit.Point);
        heading.Text = "Install " + BuildIdentity.ProductName;
        Controls.Add(heading);

        Label description = new Label();
        description.Location = new Point(30, 62);
        description.Size = new Size(510, 40);
        description.ForeColor = Color.FromArgb(72, 82, 88);
        description.Text = "The application and bundled FreeCAD runtime will be installed for your Windows account.";
        Controls.Add(description);

        progressBar = new ProgressBar();
        progressBar.Location = new Point(30, 116);
        progressBar.Size = new Size(510, 24);
        progressBar.Minimum = 0;
        progressBar.Maximum = 100;
        Controls.Add(progressBar);

        statusLabel = new Label();
        statusLabel.Location = new Point(30, 148);
        statusLabel.Size = new Size(510, 38);
        statusLabel.ForeColor = Color.FromArgb(72, 82, 88);
        statusLabel.Text = "Ready to install " + BuildIdentity.ProductVersion + ".";
        Controls.Add(statusLabel);

        desktopShortcut = new CheckBox();
        desktopShortcut.AutoSize = true;
        desktopShortcut.Location = new Point(30, 198);
        desktopShortcut.Text = "Create a desktop shortcut";
        Controls.Add(desktopShortcut);

        installButton = new Button();
        installButton.Location = new Point(346, 246);
        installButton.Size = new Size(94, 32);
        installButton.Text = "Install";
        installButton.Click += InstallButtonClick;
        Controls.Add(installButton);
        AcceptButton = installButton;

        cancelButton = new Button();
        cancelButton.Location = new Point(448, 246);
        cancelButton.Size = new Size(94, 32);
        cancelButton.Text = "Cancel";
        cancelButton.Click += CancelButtonClick;
        Controls.Add(cancelButton);
        CancelButton = cancelButton;

        worker = new BackgroundWorker();
        worker.WorkerReportsProgress = true;
        worker.WorkerSupportsCancellation = true;
        worker.DoWork += InstallPackage;
        worker.ProgressChanged += InstallationProgressChanged;
        worker.RunWorkerCompleted += InstallationCompleted;
    }

    internal int ExitCode { get; private set; }

    protected override void OnFormClosing(FormClosingEventArgs eventArgs)
    {
        if (worker.IsBusy)
        {
            worker.CancelAsync();
            statusLabel.Text = "Cancelling installation...";
            eventArgs.Cancel = true;
        }
        base.OnFormClosing(eventArgs);
    }

    private void InstallButtonClick(object sender, EventArgs eventArgs)
    {
        if (installationStarted)
        {
            Close();
            return;
        }

        installationStarted = true;
        installButton.Enabled = false;
        desktopShortcut.Enabled = false;
        statusLabel.Text = "Preparing installer payload...";
        worker.RunWorkerAsync(desktopShortcut.Checked);
    }

    private void CancelButtonClick(object sender, EventArgs eventArgs)
    {
        if (worker.IsBusy)
        {
            worker.CancelAsync();
            cancelButton.Enabled = false;
            statusLabel.Text = "Cancelling installation...";
            return;
        }
        Close();
    }

    private void InstallPackage(object sender, DoWorkEventArgs eventArgs)
    {
        BackgroundWorker backgroundWorker = (BackgroundWorker)sender;
        bool createDesktopShortcut = (bool)eventArgs.Argument;
        string installRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Programs",
            BuildIdentity.ProductName);
        string stagingRoot = installRoot + ".installing-" + Process.GetCurrentProcess().Id;

        if (Directory.Exists(stagingRoot))
        {
            Directory.Delete(stagingRoot, true);
        }
        Directory.CreateDirectory(stagingRoot);

        try
        {
            using (EmbeddedPackage.PackageArchive package = EmbeddedPackage.Open())
            {
                long totalBytes = 0;
                foreach (ZipArchiveEntry entry in package.Archive.Entries)
                {
                    if (entry.Name.Length > 0)
                    {
                        totalBytes += entry.Length;
                    }
                }

                long completedBytes = 0;
                int lastPercent = -1;
                byte[] buffer = new byte[1024 * 1024];
                foreach (ZipArchiveEntry entry in package.Archive.Entries)
                {
                    if (backgroundWorker.CancellationPending)
                    {
                        eventArgs.Cancel = true;
                        return;
                    }

                    string relativePath = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                    string destination = SafeDestinationPath(stagingRoot, relativePath);
                    if (entry.Name.Length == 0)
                    {
                        Directory.CreateDirectory(destination);
                        continue;
                    }

                    string destinationDirectory = Path.GetDirectoryName(destination);
                    if (!string.IsNullOrEmpty(destinationDirectory))
                    {
                        Directory.CreateDirectory(destinationDirectory);
                    }

                    using (Stream source = entry.Open())
                    using (FileStream target = File.Create(destination))
                    {
                        int read;
                        while ((read = source.Read(buffer, 0, buffer.Length)) > 0)
                        {
                            if (backgroundWorker.CancellationPending)
                            {
                                eventArgs.Cancel = true;
                                return;
                            }
                            target.Write(buffer, 0, read);
                            completedBytes += read;
                            int percent = totalBytes == 0
                                ? 0
                                : (int)Math.Min(97, completedBytes * 97L / totalBytes);
                            if (percent != lastPercent)
                            {
                                lastPercent = percent;
                                backgroundWorker.ReportProgress(percent, "Installing " + entry.Name + "...");
                            }
                        }
                    }
                }
            }

            backgroundWorker.ReportProgress(98, "Finalizing installation...");
            if (Directory.Exists(installRoot))
            {
                Directory.Delete(installRoot, true);
            }
            Directory.Move(stagingRoot, installRoot);
            CreateApplicationFoldersAndShortcuts(installRoot, createDesktopShortcut);
            backgroundWorker.ReportProgress(100, "Installation complete.");
        }
        finally
        {
            if (Directory.Exists(stagingRoot))
            {
                Directory.Delete(stagingRoot, true);
            }
        }
    }

    private static void CreateApplicationFoldersAndShortcuts(string installRoot, bool createDesktopShortcut)
    {
        string projectRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            "AAVDSProjects");
        string startMenuRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
            BuildIdentity.ProductName);
        Directory.CreateDirectory(projectRoot);
        Directory.CreateDirectory(startMenuRoot);

        string python = Path.Combine(installRoot, "FreeCAD", "bin", "pythonw.exe");
        string application = Path.Combine(installRoot, "app", "Allshield_Project_GUI.py");
        string freeCad = Path.Combine(installRoot, "FreeCAD", "bin", "freecad.exe");
        string applicationArguments = Quote(application) + " --project " + Quote(projectRoot);
        CreateShortcut(
            Path.Combine(startMenuRoot, BuildIdentity.ProductName + ".lnk"),
            python,
            applicationArguments,
            Path.Combine(installRoot, "app"),
            freeCad);

        string powershell = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.System),
            "WindowsPowerShell",
            "v1.0",
            "powershell.exe");
        string uninstaller = Path.Combine(installRoot, "Uninstall-AAVDS.ps1");
        CreateShortcut(
            Path.Combine(startMenuRoot, "Uninstall " + BuildIdentity.ProductName + ".lnk"),
            powershell,
            "-NoProfile -ExecutionPolicy Bypass -File " + Quote(uninstaller),
            Path.GetTempPath(),
            freeCad);

        string desktopLink = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            BuildIdentity.ProductName + ".lnk");
        if (createDesktopShortcut)
        {
            CreateShortcut(
                desktopLink,
                python,
                applicationArguments,
                Path.Combine(installRoot, "app"),
                freeCad);
        }
        else if (File.Exists(desktopLink))
        {
            File.Delete(desktopLink);
        }

        WriteInstallRecord(installRoot, projectRoot);
    }

    private void InstallationProgressChanged(object sender, ProgressChangedEventArgs eventArgs)
    {
        progressBar.Value = Math.Max(progressBar.Minimum, Math.Min(progressBar.Maximum, eventArgs.ProgressPercentage));
        statusLabel.Text = Convert.ToString(eventArgs.UserState);
    }

    private void InstallationCompleted(object sender, RunWorkerCompletedEventArgs eventArgs)
    {
        cancelButton.Enabled = true;
        if (eventArgs.Cancelled)
        {
            ExitCode = 2;
            statusLabel.Text = "Installation was cancelled.";
        }
        else if (eventArgs.Error != null)
        {
            ExitCode = 1;
            statusLabel.Text = "Installation failed.";
            MessageBox.Show(
                eventArgs.Error.Message,
                BuildIdentity.ProductName + " Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
        else
        {
            ExitCode = 0;
            progressBar.Value = 100;
            statusLabel.Text = "Installation complete. Open " + BuildIdentity.ProductName + " from the Start menu.";
        }

        installButton.Enabled = true;
        installButton.Text = ExitCode == 0 ? "Finish" : "Close";
        cancelButton.Visible = false;
    }

    private static string SafeDestinationPath(string root, string relativePath)
    {
        string fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        string destination = Path.GetFullPath(Path.Combine(fullRoot, relativePath));
        if (!destination.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("Unsafe package path: " + relativePath);
        }
        return destination;
    }

    private static string Quote(string value)
    {
        return "\"" + value + "\"";
    }

    private static void CreateShortcut(
        string shortcutPath,
        string targetPath,
        string arguments,
        string workingDirectory,
        string iconPath)
    {
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType == null)
        {
            throw new InvalidOperationException("Windows Script Host is unavailable.");
        }

        object shell = Activator.CreateInstance(shellType);
        object shortcut = null;
        try
        {
            shortcut = shellType.InvokeMember(
                "CreateShortcut",
                BindingFlags.InvokeMethod,
                null,
                shell,
                new object[] { shortcutPath });
            Type shortcutType = shortcut.GetType();
            shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { targetPath });
            shortcutType.InvokeMember("Arguments", BindingFlags.SetProperty, null, shortcut, new object[] { arguments });
            shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut, new object[] { workingDirectory });
            shortcutType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut, new object[] { iconPath });
            shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
        }
        finally
        {
            if (shortcut != null && Marshal.IsComObject(shortcut))
            {
                Marshal.FinalReleaseComObject(shortcut);
            }
            if (Marshal.IsComObject(shell))
            {
                Marshal.FinalReleaseComObject(shell);
            }
        }
    }

    private static void WriteInstallRecord(string installRoot, string projectRoot)
    {
        string json = "{\r\n" +
            "  \"product\": \"" + BuildIdentity.ProductName + "\",\r\n" +
            "  \"version\": \"" + BuildIdentity.ProductVersion + "\",\r\n" +
            "  \"installedUtc\": \"" + DateTime.UtcNow.ToString("o") + "\",\r\n" +
            "  \"installRoot\": \"" + EscapeJson(installRoot) + "\",\r\n" +
            "  \"projectRoot\": \"" + EscapeJson(projectRoot) + "\",\r\n" +
            "  \"signed\": " + (BuildIdentity.Signed ? "true" : "false") + "\r\n" +
            "}\r\n";
        File.WriteAllText(Path.Combine(installRoot, "install.json"), json, new UTF8Encoding(false));
    }

    private static string EscapeJson(string value)
    {
        return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
    }
}