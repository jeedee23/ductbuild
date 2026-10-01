using System;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("AAVDS-duct-builder Setup")]
[assembly: AssemblyDescription("Installs AAVDS-duct-builder and its bundled FreeCAD runtime")]
[assembly: AssemblyCompany("Johan Degraeve")]
[assembly: AssemblyProduct("AAVDS-duct-builder")]
[assembly: AssemblyVersion("2026.1.0.0")]
[assembly: AssemblyFileVersion("2026.1.0.0")]

internal static class InstallerLauncher
{
    [STAThread]
    private static int Main(string[] arguments)
    {
        if (arguments.Length == 1 && string.Equals(arguments[0], "--verify", StringComparison.OrdinalIgnoreCase))
        {
            return VerifyPackage();
        }

        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        try
        {
            using (EmbeddedPackage.PackageArchive package = EmbeddedPackage.Open())
            {
                EmbeddedPackage.Verify(package.Archive);
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "The installer package is incomplete or damaged.\r\n\r\n" + error.Message,
                BuildIdentity.ProductName + " Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 1;
        }

        using (InstallerForm installer = new InstallerForm())
        {
            Application.Run(installer);
            return installer.ExitCode;
        }
    }

    private static int VerifyPackage()
    {
        try
        {
            using (EmbeddedPackage.PackageArchive package = EmbeddedPackage.Open())
            {
                EmbeddedPackage.Verify(package.Archive);
            }
            return 0;
        }
        catch
        {
            return 1;
        }
    }
}