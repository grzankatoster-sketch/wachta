using Wachta.Db;

var cs = Environment.GetEnvironmentVariable("ConnectionStrings__Wachta")
    ?? throw new InvalidOperationException("ConnectionStrings__Wachta is not set");
DbMigrator.Migrate(cs);
Console.WriteLine("Migrations applied.");
